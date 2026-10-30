import re
from pydantic import BaseModel, ConfigDict, Field, field_validator


class Model(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)


class EmailInput(Model):
    email: str = Field(min_length=5, max_length=254)

    @field_validator('email')
    @classmethod
    def email_format(cls, value):
        if not re.fullmatch(r'[^\s@<>]+@[^\s@<>]+\.[^\s@<>]+', value):
            raise ValueError('Informe um e-mail válido.')
        return value.lower()


class Credentials(EmailInput):
    password: str = Field(min_length=12, max_length=128)


class TokenInput(Model):
    token: str = Field(min_length=20, max_length=200)


class ResetInput(TokenInput):
    password: str = Field(min_length=12, max_length=128)


class GoogleInput(Model):
    credential: str = Field(min_length=20, max_length=8192)


def valid_document(value):
    value = re.sub(r'\D', '', value)
    if len(value) not in {11, 14} or len(set(value)) == 1:
        return False
    weights = ([10,9,8,7,6,5,4,3,2], [11,10,9,8,7,6,5,4,3,2]) if len(value) == 11 else (
        [5,4,3,2,9,8,7,6,5,4,3,2], [6,5,4,3,2,9,8,7,6,5,4,3,2])
    for index, weight in enumerate(weights):
        total = sum(int(n) * w for n, w in zip(value, weight))
        remainder = total % 11
        if int(value[len(weight)]) != (0 if remainder < 2 else 11 - remainder):
            return False
    return True


class Registrant(Model):
    name: str = Field(min_length=3, max_length=100)
    company: str = Field(default='', max_length=100)
    document: str = Field(min_length=11, max_length=18)
    address: str = Field(min_length=5, max_length=64)
    city: str = Field(min_length=2, max_length=64)
    state: str = Field(pattern=r'^[A-Z]{2}$')
    zipcode: str = Field(pattern=r'^\d{8}$')
    phone: str = Field(pattern=r'^\d{10,11}$')

    @field_validator('document')
    @classmethod
    def document_format(cls, value):
        if not valid_document(value):
            raise ValueError('CPF ou CNPJ inválido.')
        return re.sub(r'\D', '', value)


class CheckoutInput(Model):
    quote_id: str = Field(min_length=20, max_length=100)
    registrant: Registrant
    accepted_terms: bool


def split_domain(query, tlds):
    value = query.strip().lower().rstrip('.')
    if len(value) > 253 or not value or '://' in value or '/' in value or '@' in value:
        raise ValueError('Digite somente o nome ou domínio, sem https:// ou barras.')
    selected = list(tlds)
    if '.' in value:
        label, suffix = value.split('.', 1)
        if suffix not in tlds:
            raise ValueError('Essa extensão ainda não está disponível na loja.')
        value, selected = label, [suffix]
    try:
        value = value.encode('idna').decode('ascii')
    except UnicodeError:
        raise ValueError('Nome de domínio inválido.') from None
    # IDNs require registry-specific policies; do not sell them before validation.
    if value.startswith('xn--') or not re.fullmatch(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?', value):
        raise ValueError('Use até 63 letras sem acentos, números ou hífen no meio do nome.')
    return value, selected
