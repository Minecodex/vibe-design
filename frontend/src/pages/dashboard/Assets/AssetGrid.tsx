import { type AssetRead } from '@/api/endpoints/assets';
import { AssetCard } from './AssetCard';
import { useTranslation } from 'react-i18next';
import { type RefObject, useMemo } from 'react';
import { VirtualizedSectionGrid } from '@/components/ui/VirtualizedSectionGrid';

interface AssetGridProps {
    assets: AssetRead[];
    isBatchMode: boolean;
    selectedAssets: Set<number>;
    onSelectAsset: (id: number, selected: boolean) => void;
    onRefresh: () => void;
    projectId?: number;
    activeTab?: string;
    onPreview?: (index: number) => void;
    scrollContainerRef: RefObject<HTMLElement>;
}

export function AssetGrid({
    assets,
    isBatchMode,
    selectedAssets,
    onSelectAsset,
    onRefresh,
    projectId,
    activeTab,
    onPreview,
    scrollContainerRef,
}: AssetGridProps) {
    const { t } = useTranslation();

    const groups = useMemo(() => {
        const now = new Date();
        const oneDayMs = 24 * 60 * 60 * 1000;
        const sevenDaysMs = 7 * oneDayMs;

        const results = [
            { key: 'within_1_day', title: t('within_1_day', 'Within 1 Day'), items: [] as AssetRead[] },
            { key: 'within_7_days', title: t('within_7_days', 'Within 7 Days'), items: [] as AssetRead[] },
            { key: 'older_than_7_days', title: t('older_than_7_days', 'Older than 7 Days'), items: [] as AssetRead[] }
        ];

        assets.forEach(asset => {
            const effectiveTimestamp = asset.updated_at || asset.created_at;
            // Backend date string might be "YYYY-MM-DD HH:MM:SS"
            // To be safe for all JS engines, replace space with T
            const dateStr = effectiveTimestamp.includes('T') ? effectiveTimestamp : effectiveTimestamp.replace(' ', 'T');
            const createdAt = new Date(dateStr);
            const diff = now.getTime() - createdAt.getTime();

            if (diff < oneDayMs) {
                results[0].items.push(asset);
            } else if (diff < sevenDaysMs) {
                results[1].items.push(asset);
            } else {
                results[2].items.push(asset);
            }
        });

        return results.filter(g => g.items.length > 0);
    }, [assets, t]);

    if (assets.length === 0) return null;

    return (
        <VirtualizedSectionGrid
            scrollContainerRef={scrollContainerRef}
            sections={groups}
            headerClassName="text-base font-semibold text-foreground"
            itemsRowClassName="w-full"
            renderItem={(asset, absoluteIndex) => (
                <AssetCard
                    key={asset.id}
                    asset={asset}
                    isBatchMode={isBatchMode}
                    isSelected={selectedAssets.has(asset.id)}
                    onSelect={(selected: boolean) => onSelectAsset(asset.id, selected)}
                    onRefresh={onRefresh}
                    projectId={projectId}
                    activeTab={activeTab}
                    onClick={() => {
                        if (onPreview) onPreview(absoluteIndex);
                    }}
                />
            )}
        />
    );
}
