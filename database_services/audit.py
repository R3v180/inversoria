from __future__ import annotations


def get_audit_events(get_connection, limit=200, event_type=None, symbol=None):
    where = []
    params = []
    if event_type:
        where.append("event_type = ?")
        params.append(str(event_type))
    if symbol:
        where.append("symbol = ?")
        params.append(str(symbol))
    params.append(max(1, min(int(limit), 1000)))
    sql = "SELECT * FROM audit_events"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY timestamp DESC LIMIT ?"
    with get_connection() as conn:
        rows = conn.execute(sql, tuple(params)).fetchall()
    return [dict(row) for row in rows]


def get_cycle_replay_snapshots(get_connection, limit=100, cycle_id=None):
    params = []
    sql = "SELECT * FROM cycle_replay_snapshots"
    if cycle_id:
        sql += " WHERE cycle_id = ?"
        params.append(str(cycle_id))
    sql += " ORDER BY timestamp DESC LIMIT ?"
    params.append(max(1, min(int(limit), 1000)))
    with get_connection() as conn:
        rows = conn.execute(sql, tuple(params)).fetchall()
    return [dict(row) for row in rows]

