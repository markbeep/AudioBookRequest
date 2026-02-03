from enum import Enum


class LoginTypeEnum(str, Enum):
    basic = "basic"
    forms = "forms"
    oidc = "oidc"
    # Not used as a proper login type. Used to identify users accessing the API.
    api_key = "api_key"
    none = "none"
    not_set = "not_set"
