import {
  CopilotRuntime,
  createCopilotEndpoint,
  InMemoryAgentRunner,
} from "@copilotkit/runtime/v2";
import { handle } from "hono/vercel";
import { A2AAgent } from "@ag-ui/a2a";
import { A2AClient } from "@a2a-js/sdk/client";

// Create A2A client - connection errors will be handled by CopilotKit
const a2aClient = new A2AClient("http://localhost:10002");

const agent = new A2AAgent({ a2aClient });

const runtime = new CopilotRuntime({
  agents: {
    default: agent,
  },
  runner: new InMemoryAgentRunner(),
});

const app = createCopilotEndpoint({
  runtime,
  basePath: "/api/copilotkit",
});

// Wrap handlers with error handling to prevent frontend crashes
const errorHandler = (handler: ReturnType<typeof handle>) => {
  return async (req: Request, ...args: any[]) => {
    try {
      return await handler(req, ...args);
    } catch (error: any) {
      console.error("CopilotKit endpoint error:", error);
      // If it's a connection error, return a graceful response
      if (error?.message?.includes("ECONNREFUSED") || 
          error?.code === "ECONNREFUSED" ||
          error?.cause?.code === "ECONNREFUSED") {
        return new Response(
          JSON.stringify({
            error: "Backend service is not available. Please ensure the agent server is running on port 10002.",
          }),
          {
            status: 503,
            headers: { "Content-Type": "application/json" },
          }
        );
      }
      // Re-throw other errors
      throw error;
    }
  };
};

const appHandler = handle(app);
export const GET = errorHandler(appHandler);
export const POST = errorHandler(appHandler);
