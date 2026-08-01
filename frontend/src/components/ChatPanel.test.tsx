import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { ChatPanel } from "./ChatPanel";
import type { ChatMessage } from "@/lib/types";

const messages: ChatMessage[] = [
  { id: "1", role: "user", content: "Buy 5 NVDA" },
  {
    id: "2",
    role: "assistant",
    content: "Bought 5 NVDA and added PYPL to your watchlist.",
    trades: [{ ticker: "NVDA", side: "buy", quantity: 5, price: 880.5 }],
    watchlist_changes: [{ ticker: "PYPL", action: "add" }],
  },
];

function setup(overrides: Partial<React.ComponentProps<typeof ChatPanel>> = {}) {
  const props = {
    messages,
    pending: false,
    collapsed: false,
    onToggle: vi.fn(),
    onSend: vi.fn(),
    ...overrides,
  };
  render(<ChatPanel {...props} />);
  return props;
}

describe("ChatPanel", () => {
  it("renders user and assistant messages", () => {
    setup();
    expect(screen.getByTestId("chat-user")).toHaveTextContent("Buy 5 NVDA");
    expect(screen.getByTestId("chat-assistant")).toHaveTextContent(
      "Bought 5 NVDA",
    );
  });

  it("renders inline confirmations for executed actions", () => {
    setup();
    const trade = screen.getByTestId("trade-chip");
    expect(trade).toHaveTextContent("BUY");
    expect(trade).toHaveTextContent("NVDA");
    expect(trade).toHaveTextContent("$880.50");
    expect(screen.getByTestId("watchlist-chip")).toHaveTextContent("PYPL");
  });

  it("surfaces a rejected trade", () => {
    setup({
      messages: [
        {
          id: "3",
          role: "assistant",
          content: "That order did not fill.",
          trades: [
            {
              ticker: "AAPL",
              side: "buy",
              quantity: 999,
              failed: true,
              error: "insufficient cash",
            },
          ],
        },
      ],
    });
    expect(screen.getByTestId("trade-chip")).toHaveTextContent(
      "insufficient cash",
    );
  });

  it("shows a loading indicator while awaiting the assistant", () => {
    setup({ pending: true });
    expect(screen.getByTestId("chat-loading")).toBeInTheDocument();
  });

  it("sends the trimmed draft and clears the input", async () => {
    const user = userEvent.setup();
    const { onSend } = setup({ messages: [] });
    const input = screen.getByLabelText("Chat message");

    await user.type(input, "  how am I doing?  ");
    await user.click(screen.getByRole("button", { name: "SEND" }));

    expect(onSend).toHaveBeenCalledWith("how am I doing?");
    expect(input).toHaveValue("");
  });

  it("does not send while a response is pending", async () => {
    const user = userEvent.setup();
    const { onSend } = setup({ pending: true });
    await user.type(screen.getByLabelText("Chat message"), "hello{Enter}");
    expect(onSend).not.toHaveBeenCalled();
  });

  it("collapses to a rail that can be reopened", async () => {
    const user = userEvent.setup();
    const { onToggle } = setup({ collapsed: true });
    expect(screen.queryByLabelText("Chat message")).not.toBeInTheDocument();
    await user.click(screen.getByLabelText("Open AI assistant"));
    expect(onToggle).toHaveBeenCalled();
  });
});
