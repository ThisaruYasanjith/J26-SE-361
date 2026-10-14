package lk.sliit.codecleanliness.metrics;

import java.util.HashMap;
import java.util.List;
import java.util.Map;

public class TokenSimilarityCalculator {

    public TokenSimilarity calculate(
            List<String> first,
            List<String> second) {

        Map<String, Integer> firstCounts =
                countTokens(first);

        Map<String, Integer> secondCounts =
                countTokens(second);

        int common = 0;

        for (Map.Entry<String, Integer> entry :
                firstCounts.entrySet()) {

            int secondCount = secondCounts.getOrDefault(
                    entry.getKey(), 0
            );

            common += Math.min(
                    entry.getValue(),
                    secondCount
            );
        }

        int total = first.size() + second.size();

        double score = total == 0
                ? 1.0
                : (2.0 * common) / total;

        return new TokenSimilarity(
                first.size(),
                second.size(),
                common,
                score
        );
    }

    private Map<String, Integer> countTokens(
            List<String> tokens) {

        Map<String, Integer> counts = new HashMap<>();

        for (String token : tokens) {
            counts.merge(token, 1, Integer::sum);
        }

        return counts;
    }
}