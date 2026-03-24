import { ProjectGrid } from "@/components/project/ProjectGrid"

export default function HomePage() {
  return (
    <div className="container mx-auto py-8 px-4">
      <div className="mb-8">
        <h1 className="text-3xl font-bold">Extract Agent</h1>
        <p className="text-muted-foreground mt-1">
          Upload PDF specs, extract structured context for coding agents
        </p>
      </div>
      <ProjectGrid />
    </div>
  )
}
