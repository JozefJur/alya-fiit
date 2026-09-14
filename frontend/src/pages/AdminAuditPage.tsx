import { useCallback, useEffect, useState } from "react";

import { adminApi } from "../api/endpoints";
import { ErrorMessage, Spinner, formatDateTime } from "../components/common";
import type { AuditEntry, NotificationEntry } from "../types/api";

export default function AdminAuditPage() {
  const [tab, setTab] = useState<"audit" | "outbox">("audit");
  const [entries, setEntries] = useState<AuditEntry[] | null>(null);
  const [notifications, setNotifications] = useState<NotificationEntry[] | null>(null);
  const [error, setError] = useState<unknown>(null);

  const load = useCallback(() => {
    adminApi.auditLog({ limit: 200 }).then(setEntries).catch(setError);
    adminApi.notifications().then(setNotifications).catch(setError);
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <div>
      <h1>Audit &amp; notifications</h1>
      <div className="tabs">
        <button
          type="button"
          className={tab === "audit" ? "tab active" : "tab"}
          onClick={() => setTab("audit")}
          data-testid="tab-audit"
        >
          Audit log
        </button>
        <button
          type="button"
          className={tab === "outbox" ? "tab active" : "tab"}
          onClick={() => setTab("outbox")}
          data-testid="tab-outbox"
        >
          Notification outbox
        </button>
        <button type="button" className="linklike" onClick={load}>
          ↻ Refresh
        </button>
      </div>
      <ErrorMessage error={error} />

      {tab === "audit" &&
        (!entries ? (
          <Spinner />
        ) : (
          <table className="table" data-testid="audit-table">
            <thead>
              <tr>
                <th>Time</th>
                <th>Actor</th>
                <th>Action</th>
                <th>Entity</th>
                <th>Details</th>
              </tr>
            </thead>
            <tbody>
              {entries.map((entry) => (
                <tr key={entry.id}>
                  <td className="muted">{formatDateTime(entry.created_at)}</td>
                  <td>{entry.actor_user_id ?? "system"}</td>
                  <td>
                    <code>{entry.action}</code>
                  </td>
                  <td>
                    {entry.entity_type}#{entry.entity_id}
                  </td>
                  <td className="details-cell">
                    <code>{JSON.stringify(entry.details)}</code>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        ))}

      {tab === "outbox" &&
        (!notifications ? (
          <Spinner />
        ) : (
          <table className="table" data-testid="outbox-table">
            <thead>
              <tr>
                <th>Time</th>
                <th>Recipient</th>
                <th>Type</th>
                <th>Subject</th>
                <th>Body</th>
              </tr>
            </thead>
            <tbody>
              {notifications.map((notification) => (
                <tr key={notification.id}>
                  <td className="muted">{formatDateTime(notification.created_at)}</td>
                  <td>{notification.recipient_user_id}</td>
                  <td>
                    <code>{notification.notification_type}</code>
                  </td>
                  <td>{notification.subject}</td>
                  <td className="details-cell">{notification.body}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ))}
    </div>
  );
}
