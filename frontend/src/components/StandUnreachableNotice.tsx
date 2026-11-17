import { ExternalLink, PlugZap } from "lucide-react"
import { useSupportContact } from "@/hooks/usePlatform"
import { cn } from "@/lib/utils"

/**
 * Shown when the platform could not connect to the stand at all: nothing in the
 * case can fix that, so it points to whoever looks after the platform.
 */
export function StandUnreachableNotice({ className }: { className?: string }) {
  const { data: contact } = useSupportContact()
  return (
    <div
      className={cn(
        "flex items-start gap-2 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-[0.8125rem] text-amber-900 dark:border-amber-900/60 dark:bg-amber-950/30 dark:text-amber-200",
        className,
      )}
    >
      <PlugZap className="mt-0.5 h-4 w-4 shrink-0" />
      <p className="min-w-0">
        Платформа не может подключиться к стенду — кейс тут ни при чём.
        {contact?.name && (
          <>
            {" "}Обратитесь к{" "}
            {contact.url ? (
              <a
                href={contact.url}
                target="_blank"
                rel="noreferrer"
                className="inline-flex items-center gap-0.5 font-medium underline underline-offset-2"
              >
                {contact.name}
                <ExternalLink className="h-3 w-3" />
              </a>
            ) : (
              <span className="font-medium">{contact.name}</span>
            )}
            {contact.url?.includes("mm.") ? " в Mattermost" : ""}.
          </>
        )}
      </p>
    </div>
  )
}
