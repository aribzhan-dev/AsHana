import re
import secrets

import phonenumbers
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from argon2.low_level import Type

from ashana.modules.identity.domain.models import IdentityError


class ArgonPasswords:
    def __init__(self) -> None:
        self.hasher = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=4, type=Type.ID)
        self.dummy = self.hasher.hash(secrets.token_urlsafe(32))

    def hash(self, password: str) -> str:
        return self.hasher.hash(password)

    def verify(self, hashed: str | None, password: str) -> bool:
        try:
            result = self.hasher.verify(hashed or self.dummy, password)
            return result and hashed is not None
        except (VerificationError, InvalidHashError):
            return False

    def needs_rehash(self, hashed: str) -> bool:
        return self.hasher.check_needs_rehash(hashed)


class KazakhstanMobilePhones:
    def normalize(self, phone: str) -> str:
        error = IdentityError(
            "VALIDATION_ERROR",
            "Проверьте введённые данные",
            {"phone": ["Введите мобильный номер Казахстана в формате +7"]},
        )
        if not re.fullmatch(r"[+0-9 ()-]{1,32}", phone):
            raise error
        normalized = re.sub(r"[ ()-]", "", phone)
        if not re.fullmatch(r"\+7[0-9]{10}", normalized):
            raise error
        try:
            number = phonenumbers.parse(normalized, None)
        except phonenumbers.NumberParseException:
            raise error from None
        if (
            not phonenumbers.is_valid_number(number)
            or phonenumbers.region_code_for_number(number) != "KZ"
            or phonenumbers.number_type(number) != phonenumbers.PhoneNumberType.MOBILE
        ):
            raise error
        return normalized
