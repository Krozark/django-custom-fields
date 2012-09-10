# -*- coding: utf-8 -*-
from django.contrib.contenttypes.generic import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import router, DEFAULT_DB_ALIAS
from django.db.models.fields import Field
from django.db.models.fields.related import ManyToManyRel, RelatedField, add_lazy_relation, ManyRelatedObjectsDescriptor, ReverseManyRelatedObjectsDescriptor
from django.utils.functional import curry

from django import forms
from django.utils.translation import ugettext as _, string_concat

def is_gfk_field(field):
    return isinstance(field, GenericForeignKey)

class GenericManyToManyField(RelatedField, Field):
    description = _("Generic Many-to-many relationship")

    def __init__(self, to, through, **kwargs):
        try:
            assert not to._meta.abstract, "%s cannot define a relation with abstract class %s" % (self.__class__.__name__, to._meta.object_name)
        except AttributeError: # to._meta doesn't exist, so it must be a string
            assert isinstance(to, basestring), "%s(%r) is invalid. First parameter to GenericManyToManyField must be either a model or a model name" % (self.__class__.__name__, to)

        kwargs['verbose_name'] = kwargs.get('verbose_name', None)
        self.through = through
        kwargs['rel'] = ManyToManyRel(to,
                                      related_name=kwargs.pop('related_name', None),
                                      limit_choices_to=kwargs.pop('limit_choices_to', None),
                                      symmetrical=False,
                                      through=None# Validation will fail if ManyToManyRel uses a through table that does not have a source foreign key
                                     )

        self.db_table = kwargs.pop('db_table', None)
        if kwargs['rel'].through is not None:
            assert self.db_table is None, "Cannot specify a db_table if an intermediary model is used."

        kwargs['serialize'] = False

        Field.__init__(self, **kwargs)

        msg = _('Hold down "Control", or "Command" on a Mac, to select more than one.')
        self.help_text = string_concat(self.help_text, ' ', msg)

    def _get_m2m_generic_foreign_key(self, related):
        "Function to provide the related generic foreign key for the m2m table"
        for f in self.through._meta.virtual_fields:
            if is_gfk_field(f):
                return f


    def _get_m2m_attr(self, related, attr):
        "Function that can be curried to provide the source accessor or DB column name for the m2m table"
        cache_attr = '_m2m_%s_cache' % attr
        if hasattr(self, cache_attr):
            return getattr(self, cache_attr)

        # search for a field pointing back to the source model
        for f in self.through._meta.fields:
            if hasattr(f,'rel') and f.rel and f.rel.to == related.model:
                setattr(self, cache_attr, getattr(f, attr))
                return getattr(self, cache_attr)

        # the generic relation is used as the source accessor
        f = self._get_m2m_generic_foreign_key(related)
        if f:
            setattr(self, cache_attr, getattr(f, attr))
            return getattr(self, cache_attr)


    def _get_m2m_reverse_attr(self, related, attr):
        "Function that can be curried to provide the related accessor or DB column name for the m2m table"
        cache_attr = '_m2m_reverse_%s_cache' % attr
        if hasattr(self, cache_attr):
            return getattr(self, cache_attr)
        found = False
        for f in self.through._meta.fields:
            if hasattr(f,'rel') and f.rel and f.rel.to == related.parent_model:
                if related.model == related.parent_model:
                    # If this is an m2m-intermediate to self,
                    # the first foreign key you find will be
                    # the source column. Keep searching for
                    # the second foreign key.
                    if found:
                        setattr(self, cache_attr, getattr(f, attr))
                        break
                    else:
                        found = True
                else:
                    setattr(self, cache_attr, getattr(f, attr))
                    break

        if not hasattr(self, cache_attr):
            # the generic relation is used as the related accessor
            f = self._get_m2m_generic_foreign_key(related)
            if f:
                setattr(self, cache_attr, getattr(f, attr))


        return getattr(self, cache_attr)

    def _get_column_for_field(self, related, fieldname):
        relation = getattr(self.through, fieldname())
        if is_gfk_field(relation):
            return relation.fk_field 
        else:
            return relation.field.column

    def contribute_to_class(self, cls, name):
        super(GenericManyToManyField, self).contribute_to_class(cls, name)
        self.name = self.column = name
        self.model = cls
        cls._meta.add_field(self)

        setattr(cls, self.name, ReverseGenericManyRelatedObjectsDescriptor(self))

        if not cls._meta.abstract:
            if isinstance(self.through, basestring):
                def resolve_related_class(field, model, cls):
                    self.through = model
                add_lazy_relation(
                    cls, self, self.through, resolve_related_class
                )

    def contribute_to_related_class(self, cls, related):

        # Internal M2Ms (i.e., those with a related name ending with '+')
        # don't get a related descriptor.
        if not self.rel.is_hidden():
            setattr(cls, related.get_accessor_name(), GenericManyRelatedObjectsDescriptor(related))

        # Set up the accessors for the column names on the m2m table
        self.m2m_field_name = curry(self._get_m2m_attr, related, 'name')  # source
        self.m2m_reverse_field_name = curry(self._get_m2m_reverse_attr, related, 'name') # target

        self.m2m_column_name = curry(self._get_column_for_field, related, self.m2m_field_name)
        self.m2m_reverse_name = curry(self._get_column_for_field, related, self.m2m_reverse_field_name)

    def m2m_db_table(self):
        return self.through._meta.db_table

    def m2m_target_field_name(self):
        return self.model._meta.pk.name

    def m2m_reverse_target_field_name(self):
        return self.rel.to._meta.pk.name

    def set_attributes_from_rel(self):
        self.name = self.name or (self.rel.to._meta.object_name.lower() + '_' + self.rel.to._meta.pk.name)

    def save_form_data(self, instance, value):
        getattr(instance, self.name).set(*value)

    def value_from_object(self, obj):
        return getattr(obj, self.name).all()

    def related_query_name(self):
        return self.model._meta.module_name

    def formfield(self, **kwargs):
        db = kwargs.pop('using', None)
        defaults = {
            'form_class': forms.ModelMultipleChoiceField,
            'queryset': self.rel.to._default_manager.using(db).complex_filter(self.rel.limit_choices_to)
        }
        defaults.update(kwargs)
        # If initial is passed in, it's a list of related objects, but the
        # MultipleChoiceField takes a list of IDs.
        if defaults.get('initial') is not None:
            initial = defaults['initial']
            if callable(initial):
                initial = initial()
            defaults['initial'] = [i._get_pk_val() for i in initial]

        return super(GenericManyToManyField, self).formfield(**defaults)

    def db_type(self, connection=None):
        # A ManyToManyField is not represented by a single column,
        # so return None.
        return None

    def extra_filters(self, pieces, pos, negate):
        """
        Return an extra filter to the queryset so that the results are filtered
        on the appropriate content type.
        """
        if negate:
            return []

        relation = getattr(self.through, self.m2m_field_name())
        if not is_gfk_field(relation):
            return []
        content_type = ContentType.objects.get_for_model(self.model)
        prefix = "__".join(pieces[:pos + 2])
        return [("%s__%s" % (prefix, relation.ct_field),
            content_type)]

    def bulk_related_objects(self, objs, using=DEFAULT_DB_ALIAS):
        """
        Return all objects related to ``objs`` via this ``GenericRelation``.

        """
        field_name = self.related_query_name()
        return self.rel.to._base_manager.db_manager(using).filter(**{
                "%s__pk" % field_name:
                    ContentType.objects.db_manager(using).get_for_model(self.model).pk,
                "%s__in" % field_name:
                    [obj.pk for obj in objs]
                })

class ReverseGenericManyRelatedObjectsDescriptor(ReverseManyRelatedObjectsDescriptor):

    def __get__(self, instance, instance_type=None):
        if instance is not None and instance.pk is None:
            raise AttributeError("Manager must be accessed via instance")

        rel_model=self.field.rel.to
        superclass = rel_model._default_manager.__class__
        through = self.field.through

        if is_gfk_field(getattr(through, self.field.m2m_field_name())):
            RelatedManager = create_genegic_many_related_manager(superclass, through)
        else:
            RelatedManager = create_many_genegic_related_manager(superclass, through)

        manager = RelatedManager(model=rel_model, 
                                 instance=instance,
                                 source_field_name=self.field.m2m_field_name(),
                                 target_field_name=self.field.m2m_reverse_field_name(),
                                )
        return manager


    def __set__(self, instance, value):
        if instance is None:
            raise AttributeError("Manager must be accessed via instance")


        manager = self.__get__(instance)
        manager.set(*value)


class GenericManyRelatedObjectsDescriptor(ManyRelatedObjectsDescriptor):

    def __get__(self, instance, instance_type=None):
        if instance is not None and instance.pk is None:
            raise AttributeError("Manager must be accessed via instance")

        # model's default manager.
        rel_model = self.related.model
        superclass = rel_model._default_manager.__class__
        through = self.related.field.through

        if is_gfk_field(getattr(through, self.related.field.m2m_reverse_field_name())):
            RelatedManager = create_genegic_many_related_manager(superclass, through)
        else:
            RelatedManager = create_many_genegic_related_manager(superclass, through)
        
        manager = RelatedManager(model=rel_model, 
                                 instance=instance,
                                 source_field_name=self.related.field.m2m_reverse_field_name(),
                                 target_field_name=self.related.field.m2m_field_name(),
                                )

        return manager

    def __set__(self, instance, value):
        if instance is None:
            raise AttributeError("Manager must be accessed via instance")

        manager = self.__get__(instance)
        manager.set(*value)


def create_genegic_many_related_manager(superclass, through=False):

    class GenericManyToManyManager(superclass):
        def __init__(self, model, instance, source_field_name, target_field_name):
            self.through = through # generic through model
            self.model = model # source model  
            self.instance = instance  # source instance 
            self.source_field_name = source_field_name # generic accessor field (link to source)
            self.target_field_name = target_field_name # foreign key accessor field (link to target)

            self.content_type = ContentType.objects.db_manager(instance._state.db).get_for_model(instance)
            self.source = getattr(self.through, self.source_field_name)
            self.target = getattr(self.through, self.target_field_name)

            if not is_gfk_field(self.source):
                raise TypeError("'%s' (%s) generic foreign key expected" % (self.source_field_name, type(self.source)))
            

        def get_query_set(self):
            kwargs = {
                "%s__%s" % (self.target.field.rel.related_name, self.source.ct_field): self.content_type,
                "%s__%s" % (self.target.field.rel.related_name, self.source.fk_field): self.instance.pk
            }

            #return self.target.field.rel.to.objects.filter(**kwargs).distinct()
            db = self._db = router.db_for_read(self.instance.__class__, instance=self.instance)
            return superclass.get_query_set(self).using(db).filter(**kwargs).distinct()

        def _lookup_kwargs(self):
            return self.through.lookup_kwargs(self.instance)

        def add(self, *objs):

            from django.db.models import Model
            if objs:
                new_ids = set()
                for obj in objs:
                    if isinstance(obj, self.target.field.rel.to):
                        if not router.allow_relation(obj, self.instance):
                           raise ValueError('Cannot add "%r": instance is on database "%s", value is on database "%s"' %
                                               (obj, self.instance._state.db, obj._state.db))
                        new_ids.add(obj.pk)
                    elif isinstance(obj, Model):
                        raise TypeError("'%s' instance expected" % self.target.field.rel.to._meta.object_name)
                    else:
                        new_ids.add(obj)

                db = router.db_for_write(self.through.__class__, instance=self.instance)
                vals = self.through._default_manager.using(db).values_list(self.target_field_name, flat=True)
                kwargs = {
                    self.source.ct_field: self.content_type,
                    self.source.fk_field: self.instance.pk,
                    '%s__in' % self.target_field_name: new_ids,
                }

                vals = vals.filter(**kwargs)
                new_ids = new_ids - set(vals)

                # Add the ones that aren't there already
                for obj_id in new_ids:
                   self.through._default_manager.using(db).create(**{
                       self.source.ct_field: self.content_type,
                       self.source.fk_field: self.instance.pk,
                       '%s_id' % self.target_field_name: obj_id,
                   })
        add.alters_data = True

        def set(self, *objs):
            self.clear()
            self.add(*objs)

        def remove(self, *objs):

            # If there aren't any objects, there is nothing to do.
            if objs:
                # Check that all the objects are of the right type
                old_ids = set()
                for obj in objs:
                    if isinstance(obj, self.target.field.rel.to):
                        old_ids.add(obj.pk)
                    else:
                        old_ids.add(obj)
                # Remove the specified objects from the join table
                db = router.db_for_write(self.through.__class__, instance=self.instance)
                self.through._default_manager.using(db).filter(**{
                    self.source.ct_field: self.content_type,
                    self.source.fk_field: self.instance.pk,
                    '%s__in' % self.target_field_name: old_ids,
                }).delete()
        remove.alters_data = True


        def clear(self):
            self.through.objects.filter(**self._lookup_kwargs()).delete()

    return GenericManyToManyManager


def create_many_genegic_related_manager(superclass, through):
    class ManyToManyGenericManager(superclass):
        def __init__(self, model, instance, source_field_name, target_field_name):
            self.through = through # generic through model
            self.model = model # source model  
            self.instance = instance  # source instance 
            self.source_field_name = source_field_name # accessor field (link to source)
            self.target_field_name = target_field_name # accessor field (link to target)
            
            self.content_type = ContentType.objects.db_manager(self.instance._state.db).get_for_model(self.model)
            self.source = getattr(self.through, self.source_field_name)
            self.target = getattr(self.through, self.target_field_name)

            if not is_gfk_field(self.target):
                raise TypeError("'%s' (%s) generic foreign key expected" % (self.target_field_name, type(self.target)))

        def get_query_set(self):
            kwargs = {
                self.target.ct_field: self.content_type,
                self.source_field_name: self.instance
            }

            db = self._db = router.db_for_read(self.instance.__class__, instance=self.instance)
            return superclass.get_query_set(self).using(db).filter(pk__in=self.through._default_manager.using(db).filter(**kwargs).values_list(self.target.fk_field, flat=True)).distinct()


        def add(self, *objs):

            from django.db.models import Model
            if objs:
                new_ids = set()
                for obj in objs:
                    if isinstance(obj, self.model):
                        if not router.allow_relation(obj, self.instance):
                           raise ValueError('Cannot add "%r": instance is on database "%s", value is on database "%s"' %
                                               (obj, self.instance._state.db, obj._state.db))
                        new_ids.add(obj.pk)
                    elif isinstance(obj, Model):
                        raise TypeError("'%s' instance expected" % self.target.field.rel.to._meta.object_name)
                    else:
                        new_ids.add(obj)

                db = router.db_for_write(self.through.__class__, instance=self.instance)
                vals = self.through._default_manager.using(db).values_list(self.source_field_name, flat=True)
                kwargs = {
                    self.source_field_name: self.instance,
                }

                vals = vals.filter(**kwargs)
                new_ids = new_ids - set(vals)

                # Add the ones that aren't there already
                for obj_id in new_ids:
                   self.through._default_manager.using(db).create(**{
                       self.target.ct_field: self.content_type,
                       self.target.fk_field: obj_id,
                       self.source_field_name: self.instance,
                   })
        add.alters_data = True

        def set(self, *objs):
            self.clear()
            self.add(*objs)

        def remove(self, *objs):

            # If there aren't any objects, there is nothing to do.
            if objs:
                # Check that all the objects are of the right type
                old_ids = set()
                for obj in objs:
                    if isinstance(obj, self.model):
                        old_ids.add(obj.pk)
                    else:
                        old_ids.add(obj)
                # Remove the specified objects from the join table
                db = router.db_for_write(self.through.__class__, instance=self.instance)
                self.through._default_manager.using(db).filter(**{
                    self.target.ct_field: self.content_type,
                    '%s__in' % self.target.fk_field: old_ids,
                    self.source_field_name: self.instance.pk,
                }).delete()
        remove.alters_data = True

        def clear(self):
            self.through.objects.filter(**{self.source_field_name: self.instance}).delete()

    return ManyToManyGenericManager

try:
    from south.modelsinspector import add_ignored_fields
except ImportError:
    pass
else:
    add_ignored_fields(["^gm2mfield\.fields\.GenericManyToManyField"])
