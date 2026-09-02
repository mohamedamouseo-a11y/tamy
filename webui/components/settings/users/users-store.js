import { createStore } from "/js/AlpineStore.js";
import { callJsonApi } from "/js/api.js";
import { store as notificationStore } from "/components/notifications/notification-store.js";

function toast(text, type = "info") {
  notificationStore.addFrontendToastOnly(type, text, "", 4);
}

const model = {
  users: [],
  loading: false,
  draft: { username: "", password: "", role: "user" },
  async load() {
    this.loading = true;
    try {
      const result = await callJsonApi("tamy_users", { action: "list" });
      this.setUsers(result?.users || []);
    } catch (error) { toast(error?.message || "Unable to load users", "error"); }
    finally { this.loading = false; }
  },
  cleanup() { this.users = []; this.draft = { username: "", password: "", role: "user" }; },
  setUsers(users) { this.users = (users || []).map((user) => ({ ...user, newPassword: "" })); },
  async createUser() {
    if (!this.draft.username || !this.draft.password) return toast("Username and password are required", "warning");
    await this.run({ action: "create", ...this.draft }, "User created");
    this.draft = { username: "", password: "", role: "user" };
  },
  async setRole(user, role) { await this.run({ action: "update", username: user.username, role }, "Role updated"); },
  async setActive(user, active) { await this.run({ action: "update", username: user.username, active }, active ? "User enabled" : "User disabled"); },
  async resetPassword(user) {
    if (!user.newPassword) return toast("Enter a new password first", "warning");
    await this.run({ action: "update", username: user.username, password: user.newPassword }, "Password updated");
  },
  async deleteUser(user) {
    if (!window.confirm(`Delete ${user.username}?`)) return;
    await this.run({ action: "delete", username: user.username }, "User deleted");
  },
  async run(payload, successMessage) {
    this.loading = true;
    try {
      const result = await callJsonApi("tamy_users", payload);
      if (result?.ok === false) throw new Error(result.error || "Request failed");
      this.setUsers(result?.users || []);
      toast(successMessage, "success");
    } catch (error) { toast(error?.message || "User action failed", "error"); }
    finally { this.loading = false; }
  },
};

export const store = createStore("tamyUsers", model);
