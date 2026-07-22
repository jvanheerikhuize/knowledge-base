# Parametric Memory — boundary notes only

Parametric memory is knowledge baked into a model's weights during
training. This knowledge base does not (and cannot) store it. This folder
exists only to document the *boundary*: what's assumed already known by
any sufficiently capable model, so other entries don't waste space
restating common knowledge.

Add an entry here when you catch the KB (or an agent) re-deriving
something that any capable model already knows — that's a sign the
assumption should be written down instead of an entry created in
`semantic/`.

Scaffold a new entry: `../../scripts/kb.py new --type parametric "<name>"`
