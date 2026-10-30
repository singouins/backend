# Collection: events


```text
.
├── _id (UUIDField)
├── action (StringField)
├── created (DateTimeField)
├── dst (UUIDField)
├── extra (DynamicField)
├── harmful (BooleanField)
├── instance (UUIDField)
├── name (StringField)
├── src (UUIDField)
├── trigger (UUIDField)
└── type (IntField)
```

type:
- < 10: Fight Actions (reserved for Resolver)
- 10++: Generic Actions
