# pyright: reportAny=false

from typing import Any

from pydantic import BaseModel, Field
from sqlmodel import Session

from app.util.cache import StringConfigCache
from app.util.log import logger


class IndexerConfiguration[T: (str, int, bool, float, None)](BaseModel):
    display_name: str
    description: str | None = None
    default: T | None = None
    required: bool = False
    type_: type[T] = Field(exclude=True)

    def is_str(self) -> bool:
        return self.type_ is str

    def is_float(self) -> bool:
        return self.type_ is float

    def is_int(self) -> bool:
        return self.type_ is int

    def is_bool(self) -> bool:
        return self.type_ is bool


class Configurations(BaseModel):
    """
    The configurations to use for an indexer.
    Any fields of type `IndexerConfiguration` will
    be passed in as a `ValuedConfigurations` object
    to the setup method of the indexer and input
    fields will be generated for them on the frontend.
    """

    pass


class ValuedConfigurations:
    """
    Field names need to be unique across all indexers
    and match up with the fields of the `Configurations` object.
    """

    pass


class ConfigurationException(ValueError):
    pass


class MissingRequiredException(ConfigurationException):
    pass


class InvalidTypeException(ConfigurationException):
    pass


indexer_configuration_cache = StringConfigCache[str]()


def create_valued_configuration(
    config: Configurations,
    session: Session,
    *,
    check_required: bool = True,
) -> ValuedConfigurations:
    """
    Using a configuration class, it retrieves the values from
    the cache/db and handles assigning the default values as well
    as raising exceptions for required fields.
    """

    valued = ValuedConfigurations()

    configurations = vars(config)
    for key, _value in configurations.items():
        if not isinstance(_value, IndexerConfiguration):
            logger.debug("Skipping key", key=key)
            continue
        value: IndexerConfiguration[Any] = _value  # pyright: ignore[reportExplicitAny]

        config_value = indexer_configuration_cache.get(session, key)
        if config_value is None:
            config_value = value.default

        if check_required and value.required and config_value is None:
            raise MissingRequiredException(f"Configuration {key} is required")

        if config_value is None:
            setattr(valued, key, None)
        elif value.type_ is str:
            setattr(valued, key, config_value)
        elif value.type_ is int:
            try:
                setattr(valued, key, int(config_value))
            except ValueError:
                raise InvalidTypeException(f"Configuration {key} must be an integer")
        elif value.type_ is float:
            try:
                setattr(valued, key, float(config_value))
            except ValueError:
                raise InvalidTypeException(f"Configuration {key} must be a float")
        elif value.type_ is bool:
            setattr(valued, key, config_value == "1")

    return valued
