from app.internal.env_settings import Settings

disabled = Settings().app.disable_censor


def censor(value: str):
    if disabled:
        return value
    if len(value) <= 3:
        return value
    return value[0] + value[1] + "*" * (len(value) - 3) + value[-1]
