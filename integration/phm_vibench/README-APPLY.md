# Apply to PHM-Vibench

The ready-to-merge overlay uses this repository layout:

```text
packages/phm-data-factory/       # standalone installable package
src/data_factory/standalone.py   # thin PHM-Vibench bridge
src/data_factory/__init__.py     # existing API plus two bridge exports
requirements-agent.txt           # optional local-Agent dependencies
docs/phm_data_factory.md
test/test_standalone_data_factory.py
```

From the PHM-Vibench repository root, extract the overlay archive and copy its
contents into the repository, preserving paths. Then run:

```bash
pip install -e 'packages/phm-data-factory[yaml,agent,legacy]'
PYTHONPATH=. pytest -q packages/phm-data-factory/tests
pytest -q test/test_standalone_data_factory.py
```

The existing `build_data(args_data, args_task)` path is unchanged. The only new
PHM-Vibench exports are:

```python
from src.data_factory import build_agent_data_tools, build_data_repository
```

## Compatibility note

The overlay is prepared against PHM-Vibench commit
`b7e62c4c97693d058b92b63b5ec6d0b201799a4f`. If `src/data_factory/__init__.py`
has changed since that commit, copy the two imports/exports manually rather
than overwriting newer repository changes.
