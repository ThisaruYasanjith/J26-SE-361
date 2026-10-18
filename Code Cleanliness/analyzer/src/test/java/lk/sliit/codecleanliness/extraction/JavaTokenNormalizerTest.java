
package lk.sliit.codecleanliness.extraction;

import org.junit.jupiter.api.Test;

import java.util.List;

import static org.junit.jupiter.api.Assertions.*;

class JavaTokenNormalizerTest {

    private final JavaTokenNormalizer normalizer =
            new JavaTokenNormalizer();

    @Test
    void shouldIgnoreWhitespaceAndComments() {

        List<String> first = normalizer.normalizeMethodBody("""
                {
                    int value = 10;
                    return value;
                }
                """);

        List<String> second = normalizer.normalizeMethodBody("""
                {
                    // A comment
                    int value=10;

                    return value;
                }
                """);

        assertEquals(first, second);
    }

    @Test
    void shouldNormalizeDifferentIdentifierNames() {

        List<String> first = normalizer.normalizeMethodBody("""
                {
                    int total = price + tax;
                    return total;
                }
                """);

        List<String> second = normalizer.normalizeMethodBody("""
                {
                    int amount = cost + fee;
                    return amount;
                }
                """);

        assertEquals(first, second);
    }

    @Test
    void shouldPreserveDifferentOperators() {

        List<String> addition = normalizer.normalizeMethodBody("""
                {
                    return a + b;
                }
                """);

        List<String> subtraction = normalizer.normalizeMethodBody("""
                {
                    return a - b;
                }
                """);

        assertNotEquals(addition, subtraction);
    }

    @Test
    void shouldNormalizeNumericLiterals() {

        List<String> first = normalizer.normalizeMethodBody("""
                {
                    int value = 100;
                }
                """);

        List<String> second = normalizer.normalizeMethodBody("""
                {
                    int value = 500;
                }
                """);

        assertEquals(first, second);
    }
    
}
