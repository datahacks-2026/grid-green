"use client";

const KEY = "gridgreen.session_id";

export function getSessionId(): string {
  if (typeof window === "undefined") return "ssr";
  let id = window.localStorage.getItem(KEY);
  if (!id) {
    id = `sess_${crypto.randomUUID()}`;
    window.localStorage.setItem(KEY, id);
  }
  return id;
}
