import { QueryClient } from "@tanstack/react-query";
import { beforeEach, describe, expect, it } from "vitest";

import { clearToken, endSession, getToken, setToken, startSession } from "@/lib/session";

describe("session", () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  it("round-trips a token", () => {
    setToken("abc123");
    expect(getToken()).toBe("abc123");
    clearToken();
    expect(getToken()).toBeNull();
  });

  it("trims a token, so a pasted newline does not break every request", () => {
    setToken("  abc123\n");
    expect(getToken()).toBe("abc123");
  });

  /**
   * The regression this guards:
   *
   * every cached query was answered for the *previous* credential, so keeping
   * any of it across a sign-in puts one person's name on screen next to another
   * person's data. It did exactly that -- the sidebar greeted the athlete who
   * had just signed out while showing the new one's session.
   */
  describe("switching accounts", () => {
    const seeded = () => {
      const queryClient = new QueryClient();
      queryClient.setQueryData(["me"], { display_name: "The Previous Person" });
      queryClient.setQueryData(["hitting", "me", "latest"], { pitches_faced: 66 });
      return queryClient;
    };

    it("drops every cached answer when a new session starts", () => {
      const queryClient = seeded();
      startSession(queryClient, "a-new-token");

      expect(queryClient.getQueryData(["me"])).toBeUndefined();
      expect(queryClient.getQueryData(["hitting", "me", "latest"])).toBeUndefined();
      expect(getToken()).toBe("a-new-token");
    });

    it("drops every cached answer when a session ends", () => {
      const queryClient = seeded();
      setToken("the-old-token");
      endSession(queryClient);

      expect(queryClient.getQueryData(["me"])).toBeUndefined();
      expect(queryClient.getQueryData(["hitting", "me", "latest"])).toBeUndefined();
      expect(getToken()).toBeNull();
    });
  });
});
