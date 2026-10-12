# ml/ — offline pipeline (P3)

Synthetic data from the kinetic model → validation → split by lot → kinetic baseline →
LightGBM quantile surrogate → evaluation with pre-registered go/no-go → packaging.
Full documentation: [`docs/p3-ml-kinetics.md`](../docs/p3-ml-kinetics.md).

```bash
pip install -e core && pip install -r ml/requirements.txt
python -m ml.generate --seed 42
python -m ml.validate --dataset ml/artifacts/datasets/<id>
python -m ml.split    --dataset ml/artifacts/datasets/<id>
python -m ml.baseline --split   ml/artifacts/splits/<dir>
python -m ml.train    --split   ml/artifacts/splits/<dir>
python -m ml.evaluate --run ml/artifacts/runs/<version> --split ml/artifacts/splits/<dir>
python -m ml.package  --run ml/artifacts/runs/<version> --report ml/reports/<version>
python -m ml.register --package ml/artifacts/models/<version> --report ml/reports/<version>
pytest -q ml/tests
```

Datasets, splits and training runs are reproducible and git-ignored; reports, the packaged
model and `artifacts/active.json` are committed. `params/go_nogo.yaml` must not be edited
after results are seen.
