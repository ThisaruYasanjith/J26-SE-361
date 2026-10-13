package lk.sliit.codecleanliness.metrics;

public record CohesionMetrics(
        String qualifiedClassName,
        int methodCount,
        int possibleMethodPairs,
        int connectedMethodPairs,
        double tcc,
        int lcom4
) {}