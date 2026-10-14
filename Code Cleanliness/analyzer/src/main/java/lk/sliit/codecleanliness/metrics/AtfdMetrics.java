package lk.sliit.codecleanliness.metrics;

import java.util.List;

public record AtfdMetrics(
        String qualifiedClassName,
        int distinctForeignFields,
        List<String> foreignFieldReferences,
        int unresolvedReferences
) {
    public AtfdMetrics {
        foreignFieldReferences = List.copyOf(foreignFieldReferences);
    }
}