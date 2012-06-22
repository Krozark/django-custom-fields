from django.db import models
import re
from django.forms.util import ValidationError
from django.utils.translation import ugettext_lazy as _

class ContextNameField(CharField):
    def clean(self, value):
        value = super(ContextNameField, self).clean(value)
        if not re.match(r'[\w_][\d\w_]+', value):
            raise ValidationError(_('A-z 1-9 _ only. (with first char not 1-9)'))
        return value
