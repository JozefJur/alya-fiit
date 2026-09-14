import { useCallback, useEffect, useState } from "react";

import { adminApi } from "../api/endpoints";
import { ErrorMessage, Spinner, formatDateTime } from "../components/common";
import type { AdminUser, Role } from "../types/api";

const ROLES: Role[] = ["customer", "warehouse_staff", "support_agent", "administrator"];

export default function AdminUsersPage() {
  const [users, setUsers] = useState<AdminUser[] | null>(null);
  const [error, setError] = useState<unknown>(null);

  const load = useCallback(() => {
    adminApi.users().then(setUsers).catch(setError);
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  if (!users) return error ? <ErrorMessage error={error} /> : <Spinner />;

  const update = async (id: number, payload: { role?: string; is_active?: boolean }) => {
    setError(null);
    try {
      await adminApi.updateUser(id, payload);
      load();
    } catch (err) {
      setError(err);
    }
  };

  return (
    <div>
      <h1>Users</h1>
      <ErrorMessage error={error} />
      <table className="table" data-testid="users-table">
        <thead>
          <tr>
            <th>E-mail</th>
            <th>Name</th>
            <th>Role</th>
            <th>Created</th>
            <th>Active</th>
          </tr>
        </thead>
        <tbody>
          {users.map((user) => (
            <tr key={user.id} data-testid={`user-row-${user.email}`}>
              <td>{user.email}</td>
              <td>{user.full_name}</td>
              <td>
                <select
                  value={user.role}
                  onChange={(e) => void update(user.id, { role: e.target.value })}
                  data-testid={`role-${user.email}`}
                >
                  {ROLES.map((role) => (
                    <option key={role} value={role}>
                      {role.replaceAll("_", " ")}
                    </option>
                  ))}
                </select>
              </td>
              <td className="muted">{formatDateTime(user.created_at)}</td>
              <td>
                <button
                  type="button"
                  className="linklike"
                  onClick={() => void update(user.id, { is_active: !user.is_active })}
                  data-testid={`active-${user.email}`}
                >
                  {user.is_active ? "✔ active" : "✖ deactivated"}
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
