package lk.sliit.codecleanliness.metrics;

import org.junit.jupiter.api.Test;

import java.util.List;

import static org.junit.jupiter.api.Assertions.*;

class TokenSimilarityCalculatorTest {

    private final TokenSimilarityCalculator calculator =
            new TokenSimilarityCalculator();

    @Test
    void shouldReturnFullSimilarityForIdenticalTokens() {

        TokenSimilarity result = calculator.calculate(
                List.of("int", "IDENTIFIER", "=", "NUMBER", ";"),
                List.of("int", "IDENTIFIER", "=", "NUMBER", ";")
        );

        assertEquals(5, result.commonTokenCount());
        assertEquals(1.0, result.similarity(), 0.0001);
    }

    @Test
    void shouldReturnPartialSimilarity() {

        TokenSimilarity result = calculator.calculate(
                List.of("A", "B", "C"),
                List.of("A", "B", "D")
        );

        assertEquals(2, result.commonTokenCount());
        assertEquals(2.0 / 3.0, result.similarity(), 0.0001);
    }

    @Test
    void shouldReturnZeroForCompletelyDifferentTokens() {

        TokenSimilarity result = calculator.calculate(
                List.of("A", "B"),
                List.of("C", "D")
        );

        assertEquals(0.0, result.similarity(), 0.0001);
    }

    @Test
    void shouldRespectRepeatedTokenCounts() {

        TokenSimilarity result = calculator.calculate(
                List.of("A", "A", "B"),
                List.of("A", "B", "B")
        );

        assertEquals(2, result.commonTokenCount());
        assertEquals(2.0 / 3.0, result.similarity(), 0.0001);
    }

    @Test
    void shouldHandleEmptySequences() {

        TokenSimilarity result = calculator.calculate(
                List.of(),
                List.of()
        );

        assertEquals(1.0, result.similarity(), 0.0001);
    }
}