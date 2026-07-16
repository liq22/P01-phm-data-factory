# Consumer patch set for phm-data-factory v0.2.0

Provider release:

- tag: `v0.2.0`
- commit: `5580fafec2ea5615f6d3276d95e1e5a948cc0f13`

Apply each patch from the corresponding clean repository root:

```bash
git am /path/to/0001-phm-vibench-data-backend.patch
git submodule update --init packages/phm-data-factory
```

```bash
git am /path/to/0002-phm-agent-benchmark-data-contract.patch
git submodule update --init src/phm_data_factory
```

The provider commit currently exists locally and is not pushed by this change.
Push the `v0.2.0` commit/tag before applying these patches on another machine,
otherwise the portable GitHub submodule URL cannot fetch the pinned object.

Validation performed before export:

- provider: `67 passed, 1 skipped`; wheel `phm_data_factory-0.2.0` built;
- PHM-Vibench: 3 backend tests passed; 7/7 configs validated;
- phm-agent-benchmark: 191 tests passed; exact submodule topology passed.
