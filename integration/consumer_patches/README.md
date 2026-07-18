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

The provider commit must be reachable from a public remote branch before these
patches are applied on another machine. Publish the immutable `v0.2.0` tag only
after the provider PR is merged.

Validation performed before export:

- provider: `67 passed, 1 skipped`; wheel `phm_data_factory-0.2.0` built;
- PHM-Vibench (`LQ_signal`, Python 3.10, Lightning 2.3.3): full maintained
  suite `132 passed, 1 skipped`; the skip was CUDA-only; 7/7 configs validated;
- phm-agent-benchmark: 191 tests passed; exact submodule topology passed.
