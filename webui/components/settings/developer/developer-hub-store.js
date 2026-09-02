import { createStore } from "/js/AlpineStore.js";
import { callJsonApi } from "/js/api.js";
import { store as notificationStore } from "/components/notifications/notification-store.js";

function toast(text, type = "info") {
  notificationStore.addFrontendToastOnly(type, text, "", 5);
}

function parseError(error, fallback) {
  const raw = String(error?.message || "").trim();
  if (!raw) return fallback;
  try {
    const parsed = JSON.parse(raw);
    return parsed?.error || fallback;
  } catch {
    return raw;
  }
}

const model = {
  loading: false,
  state: null,
  tokenDraft: "",
  commitMessage: "",
  selected: {},
  review: null,
  branches: [],

  async onOpen() {
    await this.refresh(false);
  },

  cleanup() {
    this.tokenDraft = "";
    this.commitMessage = "";
    this.selected = {};
    this.review = null;
    this.branches = [];
    this.state = null;
    this.loading = false;
  },

  async request(action, payload = {}) {
    return await callJsonApi("tamy_developer_hub", { action, ...payload });
  },

  applyState(state) {
    this.state = state || null;
    const available = new Set((state?.changed_files || []).map((item) => item.path));
    const nextSelected = {};
    for (const [path, value] of Object.entries(this.selected || {})) {
      if (value && available.has(path)) nextSelected[path] = true;
    }
    this.selected = nextSelected;
  },

  async refresh(fetchRemote = false) {
    this.loading = true;
    try {
      const result = await this.request(fetchRemote ? "refresh" : "state");
      this.applyState(result?.state);
      this.review = null;
      if (fetchRemote) toast("GitHub status refreshed", "success");
    } catch (error) {
      toast(parseError(error, "Unable to load Developer Hub"), "error");
    } finally {
      this.loading = false;
    }
  },

  async connect() {
    const token = String(this.tokenDraft || "").trim();
    if (!token) return toast("Enter a GitHub token first", "warning");
    this.loading = true;
    try {
      const result = await this.request("connect", { token });
      this.tokenDraft = "";
      this.applyState(result?.state);
      this.review = null;
      toast("GitHub connected", "success");
      await this.loadBranches(false);
    } catch (error) {
      toast(parseError(error, "GitHub connection failed"), "error");
    } finally {
      this.tokenDraft = "";
      this.loading = false;
    }
  },

  async disconnect() {
    this.loading = true;
    try {
      const result = await this.request("disconnect");
      this.applyState(result?.state);
      this.branches = [];
      this.review = null;
      toast("GitHub disconnected", "success");
    } catch (error) {
      toast(parseError(error, "Unable to disconnect GitHub"), "error");
    } finally {
      this.loading = false;
    }
  },

  async loadBranches(showToast = true) {
    if (!this.state?.connection?.connected) return;
    this.loading = true;
    try {
      const result = await this.request("branches");
      this.branches = result?.branches || [];
      if (showToast) toast("Branches loaded", "success");
    } catch (error) {
      toast(parseError(error, "Unable to load branches"), "error");
    } finally {
      this.loading = false;
    }
  },

  get changedFiles() {
    return this.state?.changed_files || [];
  },

  get selectedPaths() {
    return Object.entries(this.selected || {})
      .filter(([, value]) => Boolean(value))
      .map(([path]) => path)
      .sort();
  },

  isSelected(path) {
    return Boolean(this.selected?.[path]);
  },

  togglePath(path, checked) {
    this.selected = { ...(this.selected || {}), [path]: Boolean(checked) };
    this.invalidateReview();
  },

  selectAll() {
    const allSelected = this.changedFiles.length > 0 && this.changedFiles.every((item) => this.isSelected(item.path));
    const next = {};
    if (!allSelected) {
      for (const item of this.changedFiles) next[item.path] = true;
    }
    this.selected = next;
    this.invalidateReview();
  },

  invalidateReview() {
    this.review = null;
  },

  async reviewPush() {
    this.loading = true;
    try {
      const result = await this.request("review_push", {
        paths: this.selectedPaths,
        message: this.commitMessage,
      });
      this.review = result?.review || null;
      toast("Push review is ready", "success");
    } catch (error) {
      this.review = null;
      toast(parseError(error, "Push review failed"), "error");
    } finally {
      this.loading = false;
    }
  },

  async push() {
    if (!this.review?.review_id) return toast("Review the push first", "warning");
    this.loading = true;
    try {
      const result = await this.request("push", {
        paths: this.selectedPaths,
        message: this.commitMessage,
        review_id: this.review.review_id,
      });
      this.applyState(result?.state);
      this.review = null;
      this.selected = {};
      this.commitMessage = "";
      toast("Push completed", "success");
    } catch (error) {
      this.review = null;
      toast(parseError(error, "Push failed"), "error");
      await this.refresh(false);
    } finally {
      this.loading = false;
    }
  },

  async pull() {
    await this.runStateAction("pull", "Fast-forward pull completed", "Pull failed");
  },

  async sync() {
    await this.runStateAction("sync", "Two-way sync completed", "Sync failed");
  },

  async cleanup() {
    await this.runStateAction("cleanup", "Git maintenance completed", "Cleanup failed");
  },

  async runStateAction(action, successMessage, failureMessage) {
    this.loading = true;
    try {
      const result = await this.request(action);
      this.applyState(result?.state);
      this.review = null;
      toast(successMessage, "success");
    } catch (error) {
      toast(parseError(error, failureMessage), "error");
      await this.refresh(false);
    } finally {
      this.loading = false;
    }
  },

  shortSha(value) {
    return String(value || "").slice(0, 12) || "—";
  },

  statusLabel(file) {
    if (file?.untracked) return "Untracked";
    const status = String(file?.status || "").trim();
    if (status.includes("D")) return "Deleted";
    if (status.includes("A")) return "Added";
    if (status.includes("R")) return "Renamed";
    return "Modified";
  },
};

export const store = createStore("developerHub", model);
