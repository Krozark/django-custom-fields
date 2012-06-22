from django.db.models import CharField
import re
from django.forms.util import ValidationError
from django.utils.translation import ugettext_lazy as _

def ContextNameValidator(value):
    if bool(re.findall(r'[\w_][\d\w_]+', value)):
        raise ValidationError(_('A-z 1-9 _ only. (with first char not 1-9)'))
    return value
