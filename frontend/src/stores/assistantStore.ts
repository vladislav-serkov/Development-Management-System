import { create } from "zustand"
import type { AssistantAttachment } from "@/types/api"

interface Draft {
  text: string
  attachments: AssistantAttachment[]
}

const EMPTY_DRAFT: Draft = { text: "", attachments: [] }

interface AssistantUIState {
  open: boolean
  /** Feature key → chosen session. null = a new session; missing = the latest one. */
  sessions: Record<string, string | null>
  /** Unsent message per feature */
  drafts: Record<string, Draft>
  /** A message queued from a case card ("Исправить с ассистентом"); the panel sends it */
  outbox: { key: string; text: string; attachments: AssistantAttachment[] } | null
  /** The panel asks the case list to open a card */
  caseToOpen: { id: string; nonce: number } | null
  setOpen: (open: boolean) => void
  chooseSession: (key: string, sessionId: string | null) => void
  setText: (key: string, text: string) => void
  /** Pin context to the draft and show the panel */
  attach: (key: string, attachment: AssistantAttachment, text?: string) => void
  detach: (key: string, index: number) => void
  clearDraft: (key: string) => void
  /** Show the panel and send right away */
  sendNow: (key: string, text: string, attachment: AssistantAttachment) => void
  takeOutbox: () => void
  openCase: (id: string) => void
}

export const assistantKey = (projectSlug: string, featureName: string) => `${projectSlug}/${featureName}`

export const useAssistantStore = create<AssistantUIState>()((set) => ({
  open: false,
  sessions: {},
  drafts: {},
  outbox: null,
  caseToOpen: null,
  setOpen: (open) => set({ open }),
  chooseSession: (key, sessionId) => set((s) => ({ sessions: { ...s.sessions, [key]: sessionId } })),
  setText: (key, text) =>
    set((s) => ({ drafts: { ...s.drafts, [key]: { ...(s.drafts[key] ?? EMPTY_DRAFT), text } } })),
  attach: (key, attachment, text) =>
    set((s) => {
      const draft = s.drafts[key] ?? EMPTY_DRAFT
      // One chip per case and kind; an error of a case already says which case it is
      const kept = draft.attachments.filter(
        (a) => a.case_id !== attachment.case_id || (a.kind !== attachment.kind && a.kind !== "case"),
      )
      const redundant = attachment.kind === "case" && kept.some((a) => a.case_id === attachment.case_id)
      return {
        open: true,
        drafts: {
          ...s.drafts,
          [key]: {
            text: draft.text.trim() ? draft.text : (text ?? draft.text),
            attachments: redundant ? kept : [...kept, attachment],
          },
        },
      }
    }),
  detach: (key, index) =>
    set((s) => {
      const draft = s.drafts[key] ?? EMPTY_DRAFT
      return {
        drafts: { ...s.drafts, [key]: { ...draft, attachments: draft.attachments.filter((_, i) => i !== index) } },
      }
    }),
  clearDraft: (key) => set((s) => ({ drafts: { ...s.drafts, [key]: EMPTY_DRAFT } })),
  sendNow: (key, text, attachment) => set({ open: true, outbox: { key, text, attachments: [attachment] } }),
  takeOutbox: () => set({ outbox: null }),
  openCase: (id) => set((s) => ({ caseToOpen: { id, nonce: (s.caseToOpen?.nonce ?? 0) + 1 } })),
}))

export function useAssistantDraft(key: string): Draft {
  return useAssistantStore((s) => s.drafts[key]) ?? EMPTY_DRAFT
}
