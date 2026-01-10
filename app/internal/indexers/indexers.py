from app.internal.indexers.abstract import AbstractIndexer
from app.internal.indexers.configuration import Configurations
from app.internal.indexers.mam import MamIndexer


indexers: list[type[AbstractIndexer[Configurations]]] = [
    MamIndexer,
]
