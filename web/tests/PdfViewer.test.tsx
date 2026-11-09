import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import PdfViewer from "../src/components/documents/PdfViewer";

vi.mock("react-pdf", async () => {
  const { useEffect } = await import("react");
  return {
    pdfjs: { GlobalWorkerOptions: { workerSrc: "" } },
    Document: ({ file, onLoadSuccess, children }: { file: string; onLoadSuccess: (pdf: { numPages: number }) => void; children: unknown }) => {
      useEffect(() => onLoadSuccess({ numPages: 2 }), [onLoadSuccess]);
      return <div data-testid="pdf-document" data-file={file}>{children as never}</div>;
    },
    Page: ({ pageNumber, width }: { pageNumber: number; width: number }) => <p data-width={width}>page {pageNumber}</p>,
  };
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("PdfViewer", () => {
  it("shows the PDF one page at a time", async () => {
    const user = userEvent.setup();
    render(<PdfViewer url="/api/documents/p1/pdf" title="Lease" />);
    expect(await screen.findByText("page 1")).toBeInTheDocument();
    expect(screen.getByTestId("pdf-document")).toHaveAttribute("data-file", "/api/documents/p1/pdf");
    await user.click(screen.getByRole("button", { name: "Next page" }));
    expect(screen.getByText("page 2")).toBeInTheDocument();
    expect(screen.getByText("Page 2 of 2")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Next page" })).toBeDisabled();
  });

  it("fits the page to a narrow viewer, with the page switcher above the page", async () => {
    vi.stubGlobal("ResizeObserver", class {
      constructor(private readonly report: (entries: { contentRect: { width: number } }[]) => void) {}
      observe() { this.report([{ contentRect: { width: 358.4 } }]); }
      disconnect() {}
    });
    render(<PdfViewer url="/api/documents/p1/pdf" title="Lease" />);
    expect(await screen.findByText("page 1")).toHaveAttribute("data-width", "358");
    const nav = screen.getByText("Page 1 of 2");
    expect(nav.compareDocumentPosition(screen.getByTestId("pdf-document")) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });
});
