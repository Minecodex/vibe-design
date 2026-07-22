import { type AssetProjectSummaryRead } from '@/api/endpoints/assets';
import { cn } from '@/lib/utils';
import { Folder } from 'lucide-react';

interface ProjectFolderGridProps {
    projects: AssetProjectSummaryRead[];
    onFolderClick: (projectId: number, projectName: string) => void;
}

export function ProjectFolderGrid({
    projects,
    onFolderClick
}: ProjectFolderGridProps) {
    if (projects.length === 0) return null;

    return (
        <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6 gap-6">
            {projects.map(project => (
                <div
                    key={project.project_id}
                    className={cn(
                        'flex flex-col items-center rounded-[var(--app-radius-md)] border border-[var(--app-border)] bg-[var(--app-surface)] p-4 shadow-[var(--app-shadow-control)] transition-all hover:border-[var(--app-border-strong)] hover:bg-[var(--app-control-hover)]'
                    )}
                    onClick={() => onFolderClick(project.project_id, project.project_name || 'Untitled Project')}
                >
                    <div className={cn(
                        'mb-3 flex h-16 w-16 items-center justify-center rounded-[var(--app-radius-md)] bg-[var(--app-tint-primary)] shadow-sm'
                    )}>
                        <Folder className="h-8 w-8 text-[var(--app-primary)]" fill="currentColor" fillOpacity={0.16} />
                    </div>
                    <span className={cn(
                        'mb-1 w-full truncate px-2 text-center text-sm font-medium text-foreground'
                    )}>
                        {project.project_name || 'Untitled Project'}
                    </span>
                    <span className={cn(
                        'text-[10px] text-muted-foreground'
                    )}>
                        {project.asset_count} {project.asset_count === 1 ? 'item' : 'items'}
                    </span>
                </div>
            ))}
        </div>
    );
}
