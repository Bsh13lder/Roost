import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import DocumentsBoard from "../src/components/documents/DocumentsBoard";
import type { DocumentOut } from "../src/api/types";

const listDocumentsMock = vi.fn();
const getDocumentMock = vi.fn();
const createDocumentMock = vi.fn();
const uploadPdfMock = vi.fn();
const keepDocumentMock = vi.fn();
const deleteDocumentMock = vi.fn();
const setDocumentProjectMock = vi.fn();
vi.mock("../src/api/documents", () => ({
  listDocuments: (...a: unknown[]) => listDocumentsMock(...a),
  getDocument: (...a: unknown[]) => getDocumentMock(...a),
  createDocument: (...a: unknown[]) => createDocumentMock(...a),
  uploadPdf: (...a: unknown[]) => uploadPdfMock(...a),
  keepDocument: (...a: unknown[]) => keepDocumentMock(...a),
  deleteDocument: (...a: unknown[]) => deleteDocumentMock(...a),
  setDocumentProject: (...a: unknown[]) => setDocumentProjectMock(...a),
  pdfUrl: (id: string) => `/api/documents/${id}/pdf`,
}));
vi.mock("../src/components/documents/univer/DocEditor", () => ({
  default: ({ document }: { document: { title: string } }) => <p>doc editor for {document.title}</p>,
}));
vi.mock("../src/components/documents/univer/SheetEditor", () => ({
  default: ({ document }: { document: { title: string } }) => <p>sheet editor for {document.title}</p>,
}));
vi.mock("../src/components/documents/PdfViewer", () => ({ default: ({ url }: { url: string }) => <p>pdf viewer {url}</p> }));
let live = { bots: {}, boardVersion: { tasks: 0, money: 0, notes: 0, documents: 0 } };
vi.mock("../src/hooks/useLiveStore", () => ({ useLiveState: () => live }));

function meta(overrides: Partial<DocumentOut> = {}): DocumentOut {
  return {
    id: "d1", kind: "doc", title: "My tasks", pages: null, revision: 1, created_at: "2026-10-14T08:00:00Z",
    updated_at: "2026-10-14T08:00:00Z", created_by_bot: "b1", tainted: false, project_id: null, ...overrides,
  };
}

const DOCS = [
  meta(), meta({ id: "s1", kind: "sheet", title: "October expenses" }),
  meta({ id: "p1", kind: "pdf", title: "Lease", pages: 3, tainted: true }),
];

beforeEach(() => {
  live = { bots: {}, boardVersion: { tasks: 0, money: 0, notes: 0, documents: 0 } };
  for (const mock of [listDocumentsMock, getDocumentMock, createDocumentMock, uploadPdfMock, keepDocumentMock,
    deleteDocumentMock, setDocumentProjectMock]) mock.mockReset();
  listDocumentsMock.mockResolvedValue(DOCS);
  getDocumentMock.mockImplementation(async (id: string) => ({
    ...DOCS.find((doc) => doc.id === id), payload: id === "p1" ? null : {},
  }));
});
afterEach(() => cleanup());

const rowOf = async (title: string) => (await screen.findByRole("button", { name: title })).closest("li") as HTMLElement;

describe("DocumentsBoard", () => {
  it("lists documents with their kind and marks an uploaded PDF as web content", async () => {
    render(<DocumentsBoard />);
    expect(within(await rowOf("My tasks")).getByRole("img", { name: "Doc" })).toBeInTheDocument();
    expect(within(await rowOf("October expenses")).getByRole("img", { name: "Sheet" })).toBeInTheDocument();
    const lease = await rowOf("Lease");
    expect(within(lease).getByRole("img", { name: "PDF" })).toBeInTheDocument();
    expect(within(lease).getByText("from web content")).toBeInTheDocument();
  });

  it("opens a doc in the doc editor and goes back to the list", async () => {
    const user = userEvent.setup();
    render(<DocumentsBoard />);
    await user.click(await screen.findByRole("button", { name: "My tasks" }));
    expect(await screen.findByText("doc editor for My tasks")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "← Documents" }));
    expect(await screen.findByRole("button", { name: "Lease" })).toBeInTheDocument();
  });

  it("opens a sheet in the sheet editor and a PDF in the viewer", async () => {
    const user = userEvent.setup();
    render(<DocumentsBoard />);
    await user.click(await screen.findByRole("button", { name: "October expenses" }));
    expect(await screen.findByText("sheet editor for October expenses")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "← Documents" }));
    await user.click(await screen.findByRole("button", { name: "Lease" }));
    expect(await screen.findByText("pdf viewer /api/documents/p1/pdf")).toBeInTheDocument();
  });

  it("New sheet creates one and opens it", async () => {
    const created = meta({ id: "s2", kind: "sheet", title: "Untitled sheet" });
    createDocumentMock.mockResolvedValue(created);
    getDocumentMock.mockResolvedValue({ ...created, payload: {} });
    const user = userEvent.setup();
    render(<DocumentsBoard />);
    await user.click(await screen.findByRole("button", { name: "New sheet" }));
    expect(createDocumentMock).toHaveBeenCalledWith({ kind: "sheet", title: "Untitled sheet" });
    expect(await screen.findByText("sheet editor for Untitled sheet")).toBeInTheDocument();
  });

  it("uploads a PDF file and opens it", async () => {
    const uploaded = meta({ id: "p2", kind: "pdf", title: "Scan", tainted: true });
    uploadPdfMock.mockResolvedValue(uploaded);
    getDocumentMock.mockResolvedValue({ ...uploaded, payload: null });
    render(<DocumentsBoard />);
    await screen.findByRole("button", { name: "Lease" });
    const file = new File(["%PDF-1.4"], "Scan.pdf", { type: "application/pdf" });
    fireEvent.change(screen.getByLabelText("PDF file"), { target: { files: [file] } });
    await waitFor(() => expect(uploadPdfMock).toHaveBeenCalledWith(file));
    expect(await screen.findByText("pdf viewer /api/documents/p2/pdf")).toBeInTheDocument();
  });

  it("deletes only after you confirm, and Keep vouches for a web-made one", async () => {
    deleteDocumentMock.mockResolvedValue(undefined);
    keepDocumentMock.mockResolvedValue(meta({ id: "p1", tainted: false }));
    const user = userEvent.setup();
    render(<DocumentsBoard />);
    await user.click(within(await rowOf("My tasks")).getByRole("button", { name: "Delete My tasks" }));
    expect(deleteDocumentMock).not.toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: "Delete My tasks for good" }));
    expect(deleteDocumentMock).toHaveBeenCalledWith("d1");
    await user.click(within(await rowOf("Lease")).getByRole("button", { name: "Keep Lease as yours" }));
    expect(keepDocumentMock).toHaveBeenCalledWith("p1");
  });

  it("reloads when a documents_changed frame arrives", async () => {
    const { rerender } = render(<DocumentsBoard />);
    await screen.findByRole("button", { name: "Lease" });
    live = { bots: {}, boardVersion: { tasks: 0, money: 0, notes: 0, documents: 1 } };
    rerender(<DocumentsBoard />);
    await waitFor(() => expect(listDocumentsMock).toHaveBeenCalledTimes(2));
  });
});

describe("DocumentsBoard in a project", () => {
  it("lists and makes only that project's documents", async () => {
    const created = meta({ id: "d2", title: "Untitled doc", project_id: "p1" });
    createDocumentMock.mockResolvedValue(created);
    getDocumentMock.mockResolvedValue({ ...created, payload: {} });
    const user = userEvent.setup();
    render(<DocumentsBoard projectId="p1" />);
    await user.click(await screen.findByRole("button", { name: "New doc" }));
    expect(listDocumentsMock).toHaveBeenCalledWith(undefined, { projectId: "p1" });
    expect(createDocumentMock).toHaveBeenCalledWith({ kind: "doc", title: "Untitled doc", project_id: "p1" });
    expect(await screen.findByText("doc editor for Untitled doc")).toBeInTheDocument();
  });

  it("puts an uploaded PDF in the project, then opens it", async () => {
    const uploaded = meta({ id: "p2", kind: "pdf", title: "Scan", tainted: true });
    uploadPdfMock.mockResolvedValue(uploaded);
    setDocumentProjectMock.mockResolvedValue({ ...uploaded, project_id: "p1" });
    getDocumentMock.mockResolvedValue({ ...uploaded, payload: null });
    render(<DocumentsBoard projectId="p1" />);
    await screen.findByRole("button", { name: "Lease" });
    const file = new File(["%PDF-1.4"], "Scan.pdf", { type: "application/pdf" });
    fireEvent.change(screen.getByLabelText("PDF file"), { target: { files: [file] } });
    await waitFor(() => expect(setDocumentProjectMock).toHaveBeenCalledWith("p2", "p1"));
    expect(await screen.findByText("pdf viewer /api/documents/p2/pdf")).toBeInTheDocument();
  });
});
