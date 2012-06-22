from django.db.models import CharField
import re
from django.forms.util import ValidationError
from django.utils.translation import ugettext_lazy as _

def ContextNameValidator(value):
    r = re.findall(r'[\w_][\d\w_]+', value)
    if not(bool(re) and len(r) == 1):
        raise FormValidationError(_('A-z 1-9 _ only. (with first char not 1-9)'))
    return value
