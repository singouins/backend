# -*- coding: utf8 -*-

import json
import os

from loguru import logger
from pymongo import ReplaceOne

from mongo.models.Meta import (
    MetaArmor,
    MetaConsumable,
    MetaMap,
    MetaRace,
    MetaRecipe,
    MetaWeapon,
    )

# Relative to this package, not to the cwd of whoever runs it
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')

# Metafiles location for Mongo init
META_FILES = {
    MetaArmor: 'metas/armors.json',
    MetaConsumable: 'metas/consumables.json',
    MetaRace: 'metas/races.json',
    MetaRecipe: 'metas/recipes.json',
    MetaWeapon: 'metas/weapons.json',
}
# Mapfiles location for Mongo init
MAP_FILES = {
    1: 'maps/1.json',
    2: 'maps/2.json',
}


def _load(filename):
    with open(os.path.join(DATA_DIR, filename), 'r') as file:
        return json.load(file)


def _replace_all(documents):
    """
    Writes every document as is, replacing the stored one with the same _id
    (or inserting it). Running it again changes nothing, and two concurrent
    runs can't clash on a duplicate key.
    """
    if not documents:
        return
    for document in documents:
        document.validate()
    collection = type(documents[0])._get_collection()
    collection.bulk_write(
        [ReplaceOne({'_id': doc.pk}, doc.to_mongo(), upsert=True) for doc in documents]
        )
    logger.debug(f'MongoDB init: OK singouins/{collection.name} ({len(documents)})')


# Load JSON meta files into DB, replacing what's there
def initialize_mongodb_meta():
    for model, filename in META_FILES.items():
        documents = []
        for meta in _load(filename):
            # Needed to force ID creation in mongo
            meta['_id'] = meta.pop('id')
            documents.append(model(**meta))
        _replace_all(documents)

    logger.info('MongoDB init: OK singouins/_meta*')


# Load JSON map files into DB, replacing what's there
def initialize_mongodb_map():
    documents = []
    for map_id, filename in MAP_FILES.items():
        map_data = _load(filename)
        documents.append(
            MetaMap(
                _id=map_id,
                size=f"{map_data['height']}x{map_data['width']}",
                data=map_data,
                )
            )
    _replace_all(documents)

    logger.info('MongoDB init: OK singouins/_maps/*')
