import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { App } from "./App";
import "./index.css";
import { createEngine, createTauriTransport, isTauri } from "./lib/engine";
import type { Engine } from "./lib/engine";
import { AdminProvider } from "./state/AdminContext";
import { EngineProvider } from "./state/EngineContext";

async function boot(): Promise<Engine | null> {
  // `--mode demo` derlemesi (müşteri demosu: tek HTML veya taşınabilir exe) her zaman örnek veri
  // motorunu kullanır; normal üretim paketine demo motoru girmez. Arayüz "DEMO" şeridi gösterir.
  if (import.meta.env.MODE === "demo") {
    const { createMockTransport } = await import("./lib/mock");
    return createEngine(createMockTransport(), true);
  }
  if (isTauri()) {
    return createEngine(await createTauriTransport(), false);
  }
  if (import.meta.env.DEV) {
    const { createMockTransport } = await import("./lib/mock");
    return createEngine(createMockTransport(), true);
  }
  return null;
}

const container = document.getElementById("root");
if (container === null) throw new Error("#root bulunamadı");
const root = createRoot(container);

void boot().then((engine) => {
  if (engine === null) {
    root.render(<p style={{ padding: 24 }}>Etkileşim Takip yalnızca masaüstü uygulaması içinde çalışır.</p>);
    return;
  }
  root.render(
    <StrictMode>
      <EngineProvider engine={engine}>
        <AdminProvider>
          <App />
        </AdminProvider>
      </EngineProvider>
    </StrictMode>,
  );
});
