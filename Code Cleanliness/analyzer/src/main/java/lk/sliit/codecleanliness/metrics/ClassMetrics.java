package lk.sliit.codecleanliness.metrics;

public record ClassMetrics(
        String qualifiedClassName,
        int line,
        int classNcss,
        int methodCount,
        int fieldCount,
        int weightedMethodCount
) {}