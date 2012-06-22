from django.db import models
from django.utils.translation import ugettext_lazy as _

from django.forms.fields import Field
from django.forms.util import ValidationError as FormValidationError
from django.template import TemplateSyntaxError

from django.template.loader import get_template

class TemplateFormField(Field):
    description = "Field to store valide template path"

    def __init__(self,*args,**kwargs):
        self.max_length = kwargs.pop('max_length') or 255
        super(TemplateFormField,self).__init__(*args,**kwargs)
    
    def clean(self,value):
        if not value and not self.required:
            return None

        value = super(TemplateFormField,self).clean(value)

        if isinstance(value, basestring):
            try :
                get_template(value)
            except TemplateSyntaxError,e:
                raise FormValidationError('%s' %  e)
            except:
                raise FormValidationError(_('Template %s does not existe' % value))
        else:
            raise FormValidationError(_('Not string instance' % value))
        return value             

class TemplateField(models.CharField):
    """ Field to store valid template path"""
    __metaclass__ = models.SubfieldBase


    def db_type(self, connection):
        return 'char(%s)' % self.max_length

    def get_internal_type(self):
        return "CharField"

    #def to_python(self,value):
    #    return value             

    def get_db_prep_value(self, value, connection, prepared=False):
        return value

    def value_to_string(self, obj):
        value = self._get_val_from_obj(obj)
        return self.get_db_prep_value(value)

    def value_from_object(self, obj):
        value= super(TemplateField, self).value_from_object(obj)
        return value

    def formfield(self, **kwargs):

        if "form_class" not in kwargs:
            kwargs["form_class"] = TemplateFormField

        field = super(TemplateField, self).formfield(**kwargs)

        if not field.help_text:
            field.help_text = "Enter valide template path"

        return field


