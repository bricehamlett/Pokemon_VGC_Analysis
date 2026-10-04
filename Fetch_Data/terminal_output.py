"""Compact, human-readable console output for ingestion runs."""


def _short(value, limit=68):
    text = str(value or "Unnamed event")
    return text if len(text) <= limit else text[: limit - 1] + "…"


def event_summary(report):
    """Render one event without losing detailed data from the JSON run report."""
    reported = report.get("reported_players", 0)
    returned = report.get("returned_players", 0)
    regulation = report.get("regulation") or report.get("api_format") or "unknown"
    warnings = []
    if returned != reported:
        warnings.append(f"source count {returned:,}/{reported:,}")
    for key, label in (
        ("invalid", "invalid"),
        ("missing", "missing sheets"),
        ("unresolved", "unresolved refs"),
        ("conflicts", "conflicts"),
        ("pending_identity_entrants", "pending identities"),
    ):
        value = report.get(key, 0)
        if value:
            warnings.append(f"{label} {value:,}")

    marker = "WARN" if warnings else "OK"
    imported = report.get("imported_sheets")
    sheets = f" | new sheets +{imported:,}" if imported is not None else ""
    line = (
        f"[{marker}] {regulation} | {_short(report.get('name'))} | "
        f"players {returned:,}/{reported:,} | "
        f"placed {report.get('placement_candidates', 0):,}{sheets}"
    )
    if warnings:
        line += "\n       Review: " + ", ".join(warnings)
    return line


def error_summary(error):
    target = error.get("event_id") or error.get("format") or "unknown"
    stage = f" ({error['stage']})" if error.get("stage") else ""
    return f"[ERROR] {target}{stage}: {error.get('error', 'unknown error')}"


def wait_summary(reason, seconds):
    seconds = round(seconds)
    if reason == "rate_limit_reset":
        return f"[WAIT] API quota exhausted; resuming in {seconds:,} seconds."
    if reason == "rate_limit_or_server_retry":
        return f"[WAIT] API rate limit/server error; retrying in {seconds:,} seconds."
    return f"[WAIT] API connection retry in {seconds:,} seconds."


def final_summary(processed, failed, report_path, database_written):
    action = "imported" if database_written else "audited"
    status = "DONE" if not failed else "DONE WITH ERRORS"
    return (
        f"[{status}] {processed:,} tournaments {action}; {failed:,} failed.\n"
        f"       Detailed report: {report_path}"
    )
