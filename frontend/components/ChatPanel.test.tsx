import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

// vi.mock with importOriginal, NOT vi.spyOn: an ES module namespace object is
// sealed, so spying on one of its exports throws. Spreading the original keeps
// everything not explicitly replaced real — which matters here because the
// component branches on `err instanceof ApiError`, and a stubbed-out ApiError
// would make that branch unreachable.
vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api")>();
  return {
    ...actual,
    fetchChatHistory: vi.fn(),
    sendChatMessage: vi.fn(),
  };
});

vi.mock("@/components/PortfolioProvider", () => ({
  usePortfolioContext: () => ({
    cashBalance: 10000,
    positions: [],
    totalValue: 10000,
    loading: false,
    error: false,
    refresh: vi.fn().mockResolvedValue(undefined),
  }),
}));

import { fetchChatHistory, sendChatMessage } from "@/lib/api";
import { ChatPanel } from "@/components/ChatPanel";

const mockFetchHistory = vi.mocked(fetchChatHistory);
const mockSend = vi.mocked(sendChatMessage);

beforeEach(() => {
  vi.clearAllMocks();
});

afterEach(() => {
  vi.resetAllMocks();
});

async function sendMessage(text: string) {
  const user = userEvent.setup();
  await user.type(screen.getByPlaceholderText("Ask FinAlly…"), text);
  await user.click(screen.getByRole("button", { name: "Send message" }));
}

describe("ChatPanel transcript states", () => {
  it("renders the empty state when there is no conversation yet", async () => {
    mockFetchHistory.mockResolvedValue([]);
    render(<ChatPanel />);

    expect(await screen.findByText("Start chatting with FinAlly")).toBeInTheDocument();
  });

  it("renders a loaded conversation with role labels", async () => {
    mockFetchHistory.mockResolvedValue([
      { role: "user", content: "what do I hold?", actions: null, created_at: "2026-08-04T00:00:00Z" },
      { role: "assistant", content: "Nothing yet.", actions: [], created_at: "2026-08-04T00:00:01Z" },
    ]);
    render(<ChatPanel />);

    expect(await screen.findByText("what do I hold?")).toBeInTheDocument();
    expect(screen.getByText("Nothing yet.")).toBeInTheDocument();
    expect(screen.getByText("YOU")).toBeInTheDocument();
    expect(screen.getByText("FINALLY")).toBeInTheDocument();
  });

  it("renders the history error copy when the mount fetch fails", async () => {
    mockFetchHistory.mockRejectedValue(new Error("network"));
    render(<ChatPanel />);

    expect(
      await screen.findByText("Couldn't load your conversation — check your connection and reload."),
    ).toBeInTheDocument();
  });
});

describe("ChatPanel CR-01 regression", () => {
  // Phase 4's code review found this as a CRITICAL bug: the transcript
  // branched on a never-cleared `historyError` first, so ONE failed history
  // load permanently masked the conversation — later sends succeeded and
  // updated state behind a banner the user could never get past. The review
  // noted the component had zero test coverage. This is that coverage.
  //
  // The assertion that matters is the LAST one. A test that only checked the
  // error appears would have passed against the bug.
  it("shows the user's message and the reply after a send, even though the history load failed", async () => {
    mockFetchHistory.mockRejectedValue(new Error("network"));
    mockSend.mockResolvedValue({ message: "Here is your portfolio.", actions: [] });

    render(<ChatPanel />);
    await screen.findByText("Couldn't load your conversation — check your connection and reload.");

    await sendMessage("what do I hold?");

    await waitFor(() => {
      expect(screen.getByText("what do I hold?")).toBeInTheDocument();
    });
    // The regression: with the bug present this reply exists in state but is
    // never rendered.
    expect(await screen.findByText("Here is your portfolio.")).toBeInTheDocument();
  });
});

describe("ChatPanel send lifecycle", () => {
  it("keeps the user's message visible and shows the failure copy when a send fails", async () => {
    mockFetchHistory.mockResolvedValue([]);
    mockSend.mockRejectedValue(new Error("offline"));

    render(<ChatPanel />);
    await screen.findByText("Start chatting with FinAlly");

    await sendMessage("buy 2 AAPL");

    // A message that vanishes reads as data loss rather than a failed request.
    expect(await screen.findByText("buy 2 AAPL")).toBeInTheDocument();
    expect(
      screen.getByText("Couldn't reach FinAlly — check your connection and try again."),
    ).toBeInTheDocument();
  });

  it("renders one inline confirmation card per executed action", async () => {
    mockFetchHistory.mockResolvedValue([]);
    mockSend.mockResolvedValue({
      message: "Done.",
      actions: [
        {
          kind: "trade",
          status: "success",
          ticker: "AAPL",
          side: "buy",
          action: null,
          quantity: 2,
          price: 190,
          error: null,
        },
        {
          kind: "watchlist",
          status: "error",
          ticker: "ZZZZ",
          side: null,
          action: "add",
          quantity: null,
          price: null,
          error: "Couldn't add ZZZZ — check the symbol and try again.",
        },
      ],
    });

    render(<ChatPanel />);
    await screen.findByText("Start chatting with FinAlly");
    await sendMessage("buy 2 AAPL and add ZZZZ to my watchlist");

    // Success renders the composed sentence; failure renders the backend's
    // own sentence verbatim.
    expect(await screen.findByText("Bought 2 AAPL at $190.00")).toBeInTheDocument();
    expect(
      screen.getByText("Couldn't add ZZZZ — check the symbol and try again."),
    ).toBeInTheDocument();
  });

  it("renders no confirmation cards when the reply executed nothing", async () => {
    mockFetchHistory.mockResolvedValue([]);
    mockSend.mockResolvedValue({ message: "You hold nothing.", actions: [] });

    render(<ChatPanel />);
    await screen.findByText("Start chatting with FinAlly");
    await sendMessage("what do I hold?");

    expect(await screen.findByText("You hold nothing.")).toBeInTheDocument();
    // A card's presence is always meaningful, so absence must be too.
    expect(screen.queryByText(/^Bought /)).not.toBeInTheDocument();
    expect(screen.queryByText(/watchlist\.$/)).not.toBeInTheDocument();
  });
});
