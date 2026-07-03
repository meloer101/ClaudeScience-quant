from quantbench.monitor.pipeline import check_run_decay


def _check_run_decay(run_id: str) -> dict:
    return check_run_decay(run_id)
