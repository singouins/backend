# Collections: _meta*

DynamicDocuments: only _id is declared, the other fields come from
the JSON files loaded by `python3 -m mongo.init` (mongo/init.py).

The services don't load them: run it before starting them (a Kubernetes
Job), and again whenever mongo/data changes. Every map/meta is replaced
by its file version, so running it twice is harmless.


## _metaarmors (mongo/data/metas/armors.json)
```text
.
└── _id (IntField)
```

## _metaconsumables (mongo/data/metas/consumables.json)
```text
.
└── _id (IntField)
```

## _metaraces (mongo/data/metas/races.json)
```text
.
└── _id (IntField)
```

## _metarecipes (mongo/data/metas/recipes.json)
```text
.
└── _id (IntField)
```

## _metaweapons (mongo/data/metas/weapons.json)
```text
.
└── _id (IntField)
```


# Collection: _maps (mongo/data/maps/*.json)


```text
.
├── _id (IntField)
├── data (DynamicField) - the map JSON file
├── mode (StringField)
├── size (StringField) - "{height}x{width}"
└── type (StringField)
```
