# -*- coding: utf8 -*-
"""
Loads the maps and metas of mongo/data into MongoDB.

The services don't do it themselves: run this once before starting them
(Kubernetes Job), and again whenever mongo/data changes:

    python3 -m mongo.init

Every map/meta is replaced by its file version, so running it twice is
harmless. It exits non-zero on any error, so the Job can retry.
"""

from mongo._initialize import initialize_mongodb_map, initialize_mongodb_meta

if __name__ == '__main__':
    initialize_mongodb_map()
    initialize_mongodb_meta()
