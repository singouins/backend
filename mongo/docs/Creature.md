# Collection: creatures


```text
.
├── _id (UUIDField)
├── account (UUIDField)
├── active (BooleanField)
├── created (DateTimeField)
├── diplo (StringField)
├── gender (BooleanField)
├── hp
│   ├── base (IntField)
│   ├── current (IntField)
│   └── max (IntField)
├── instance (UUIDField)
├── korp
│   ├── id (UUIDField)
│   └── rank (StringField)
├── level (IntField)
├── name (StringField)
├── race (IntField)
├── rarity (StringField)
├── slots
│   ├── feet
│   │   ├── id (UUIDField)
│   │   ├── metaid (IntField)
│   │   └── metatype (StringField)
│   ├── hands
│   │   ├── id (UUIDField)
│   │   ├── metaid (IntField)
│   │   └── metatype (StringField)
│   ├── head
│   │   ├── id (UUIDField)
│   │   ├── metaid (IntField)
│   │   └── metatype (StringField)
│   ├── holster
│   │   ├── id (UUIDField)
│   │   ├── metaid (IntField)
│   │   └── metatype (StringField)
│   ├── lefthand
│   │   ├── id (UUIDField)
│   │   ├── metaid (IntField)
│   │   └── metatype (StringField)
│   ├── legs
│   │   ├── id (UUIDField)
│   │   ├── metaid (IntField)
│   │   └── metatype (StringField)
│   ├── righthand
│   │   ├── id (UUIDField)
│   │   ├── metaid (IntField)
│   │   └── metatype (StringField)
│   ├── shoulders
│   │   ├── id (UUIDField)
│   │   ├── metaid (IntField)
│   │   └── metatype (StringField)
│   └── torso
│       ├── id (UUIDField)
│       ├── metaid (IntField)
│       └── metatype (StringField)
├── squad
│   ├── id (UUIDField)
│   └── rank (StringField)
├── stats
│   ├── race
│   │   ├── b (IntField)
│   │   ├── g (IntField)
│   │   ├── m (IntField)
│   │   ├── p (IntField)
│   │   ├── r (IntField)
│   │   └── v (IntField)
│   ├── spec
│   │   ├── b (IntField)
│   │   ├── g (IntField)
│   │   ├── m (IntField)
│   │   ├── p (IntField)
│   │   ├── r (IntField)
│   │   └── v (IntField)
│   └── total
│       ├── b (IntField)
│       ├── g (IntField)
│       ├── m (IntField)
│       ├── p (IntField)
│       ├── r (IntField)
│       └── v (IntField)
├── targeted_by (StringField)
├── updated (DateTimeField)
├── x (IntField)
├── xp (IntField)
└── y (IntField)
```
