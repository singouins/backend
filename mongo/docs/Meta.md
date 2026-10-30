# Collections: _meta*

DynamicDocuments: only _id is declared, the other fields come from
the JSON files loaded at init (mongo/_initialize.py).


## _metaarmors (mongo/data/metas/armors.json)
.
└── _id (IntField)

## _metaconsumables (mongo/data/metas/consumables.json)
.
└── _id (IntField)

## _metaraces (mongo/data/metas/races.json)
.
└── _id (IntField)

## _metarecipes (mongo/data/metas/recipes.json)
.
└── _id (IntField)

## _metaweapons (mongo/data/metas/weapons.json)
.
└── _id (IntField)


# Collection: _maps (mongo/data/maps/*.json)


.
├── _id (IntField)
├── data (DynamicField) - the map JSON file
├── mode (StringField)
├── size (StringField) - "{height}x{width}"
└── type (StringField)