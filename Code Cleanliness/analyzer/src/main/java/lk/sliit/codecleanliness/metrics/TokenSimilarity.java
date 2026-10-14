package lk.sliit.codecleanliness.metrics;

public record TokenSimilarity(
        int firstTokenCount,
        int secondTokenCount,
        int commonTokenCount,
        double similarity
) {}