"use client";

import { CopilotChat, CopilotKitProvider } from "@copilotkit/react-core/v2";
import { createA2UIMessageRenderer } from "@copilotkit/a2ui-renderer";
import { theme } from "./theme";
import { useEffect } from "react";

// Disable static optimization for this page
export const dynamic = "force-dynamic";

const A2UIMessageRenderer = createA2UIMessageRenderer({ theme });
const activityRenderers = [A2UIMessageRenderer];

export default function Home() {
  // Add global error handler for unhandled promise rejections
  useEffect(() => {
    const handleUnhandledRejection = (event: PromiseRejectionEvent) => {
      // Log the error but don't crash the app
      console.error("Unhandled promise rejection:", event.reason);
      
      // If it's a connection error, just log it - the UI should handle it gracefully
      if (event.reason?.message?.includes("ECONNREFUSED") || 
          event.reason?.code === "ECONNREFUSED" ||
          event.reason?.cause?.code === "ECONNREFUSED") {
        console.warn("Backend connection error - this is expected if the backend hasn't started yet");
        event.preventDefault(); // Prevent the error from crashing the app
      }
    };

    window.addEventListener("unhandledrejection", handleUnhandledRejection);
    
    return () => {
      window.removeEventListener("unhandledrejection", handleUnhandledRejection);
    };
  }, []);

  return (
    <CopilotKitProvider
      runtimeUrl="/api/copilotkit"
      showDevConsole="auto"
      renderActivityMessages={activityRenderers}
    >
      <main
        className="h-full overflow-auto w-screen"
        style={{ minHeight: "100dvh" }}
      >
        <CopilotChat className="h-full" />;
      </main>
    </CopilotKitProvider>
  );
}
