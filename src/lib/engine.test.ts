import { describe, expect, it, vi } from "vitest";

import { EngineError, createEngine } from "./engine";
import type { EngineTransport } from "./engine";

function transportReturning(result: unknown) {
  const invoke = vi.fn<EngineTransport["invoke"]>().mockResolvedValue(result);
  return { transport: { invoke } satisfies EngineTransport, invoke };
}

describe("createEngine", () => {
  it("maps engine failures to EngineError with the code", async () => {
    const invoke = vi.fn<EngineTransport["invoke"]>().mockRejectedValue({ code: "UNSAFE_URL", message: "Yerel ağ adresleri kabul edilmez" });
    const engine = createEngine({ invoke }, false);
    await expect(engine.addPost({ user_id: 1, url: "http://localhost/" })).rejects.toMatchObject({
      name: "EngineError",
      code: "UNSAFE_URL",
      message: "Yerel ağ adresleri kabul edilmez",
    });
  });

  it("wraps plain string and unknown errors", async () => {
    const strings = createEngine({ invoke: vi.fn<EngineTransport["invoke"]>().mockRejectedValue("kırıldı") }, false);
    await expect(strings.health()).rejects.toBeInstanceOf(EngineError);
    const unknown = createEngine({ invoke: vi.fn<EngineTransport["invoke"]>().mockRejectedValue(42) }, false);
    await expect(unknown.health()).rejects.toMatchObject({ code: "INTERNAL" });
  });

  it("sends the admin PIN separately from the payload", async () => {
    const { transport, invoke } = transportReturning({ team_id: 7 });
    const engine = createEngine(transport, false);
    await expect(engine.addTeam("246810", "Marketing A", "")).resolves.toBe(7);
    expect(invoke).toHaveBeenCalledWith("add_team", { payload: { name: "Marketing A", chat_id: "" }, pin: "246810" });
  });

  it("never sends a PIN for ordinary commands", async () => {
    const { transport, invoke } = transportReturning({});
    const engine = createEngine(transport, false);
    await engine.state(null);
    expect(invoke.mock.calls[0]?.[1].pin).toBeNull();
  });

  it("passes settings changes and team scope", async () => {
    const { transport, invoke } = transportReturning({});
    await createEngine(transport, false).settingsSet("246810", { inactivity_days: 5 }, 2);
    expect(invoke).toHaveBeenCalledWith("settings_set", {
      payload: { changes: { inactivity_days: 5 }, team_id: 2 },
      pin: "246810",
    });
  });

  it("reports preview mode", () => {
    expect(createEngine({ invoke: vi.fn() }, true).isPreview).toBe(true);
  });
});
