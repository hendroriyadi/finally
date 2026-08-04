import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

// RTL only auto-registers its cleanup when Vitest globals are enabled, and
// this project runs without them (every identifier imported explicitly). So
// register it here: without this, each test's DOM accumulates and queries
// start failing with "found multiple elements" for reasons that have nothing
// to do with the component under test.
afterEach(() => {
  cleanup();
});

// jsdom gap, not an application workaround: jsdom does not implement
// Element.prototype.scrollIntoView at all. ChatPanel calls it from an effect
// on every transcript change, so without this stub every test in that file
// fails at mount with "scrollIntoView is not a function" — an error that
// looks nothing like a chat bug and sends you reading the wrong file.
Element.prototype.scrollIntoView = function scrollIntoView() {};
