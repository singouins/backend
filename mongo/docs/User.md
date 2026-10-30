# Collection: users


```text
.
├── _id (UUIDField)
├── active (BooleanField)
├── created (DateTimeField)
├── discord
│   ├── id (StringField) - Discord user id, unique (partial index)
│   └── name (StringField) - display only
├── hash (StringField)
├── name (StringField)
└── updated (DateTimeField)
```
