import re


class ContentValidator:

    def validate(self, content, campaign, knowledge_context=""):

        errors = []
        warnings = []

        content_lower = content.lower()

        source_text = self._build_source_text(
            campaign,
            knowledge_context
        )

        source_lower = source_text.lower()

        # -------------------------------------------------
        # 1. Discounts / percentages
        # -------------------------------------------------

        percentage_matches = re.findall(
            r"\b\d{1,3}\s?%",
            content
        )

        for percentage in percentage_matches:

            if percentage.lower() not in source_lower:
                errors.append(
                    f"Unsupported percentage or discount: {percentage}"
                )

        # -------------------------------------------------
        # 2. Coupon / promo codes
        # -------------------------------------------------

        promo_patterns = [
            r"\bcode\s+[A-Z0-9_-]{3,}\b",
            r"\bcoupon\s+[A-Z0-9_-]{3,}\b",
            r"\bpromo\s+code\s+[A-Z0-9_-]{3,}\b",
        ]

        for pattern in promo_patterns:

            matches = re.findall(
                pattern,
                content,
                flags=re.IGNORECASE
            )

            for match in matches:

                if match.lower() not in source_lower:
                    errors.append(
                        f"Unsupported promotional code: {match}"
                    )

        # -------------------------------------------------
        # 3. High-risk marketing claims
        # -------------------------------------------------

        risky_claims = [
            "limited edition",
            "limited time offer",
            "exclusive offer",
            "exclusive discount",
            "free shipping",
            "new arrival",
            "best seller",
            "bestseller",
            "guaranteed",
            "100% guaranteed",
            "premium quality",
            "high-quality materials",
            "highest quality",
            "number one",
            "#1",
        ]

        for claim in risky_claims:

            if (
                claim in content_lower
                and claim not in source_lower
            ):
                errors.append(
                    f"Unsupported claim: {claim}"
                )

        # -------------------------------------------------
        # 4. Placeholder content
        # -------------------------------------------------

        placeholders = [
            "[link",
            "[website",
            "[insert",
            "[company",
            "[product",
            "yourwebsite.com",
            "example.com",
        ]

        for placeholder in placeholders:

            if placeholder in content_lower:
                errors.append(
                    f"Placeholder detected: {placeholder}"
                )

        # -------------------------------------------------
        # 5. Make sure all 3 suggestions exist
        # -------------------------------------------------

        required_suggestions = [
            "Suggestion 1",
            "Suggestion 2",
            "Suggestion 3",
        ]

        for suggestion in required_suggestions:

            if suggestion.lower() not in content_lower:
                errors.append(
                    f"Missing required section: {suggestion}"
                )

        # -------------------------------------------------
        # 6. Required content fields
        # -------------------------------------------------

        title_count = len(
            re.findall(
                r"(?i)\bTitle\s*:",
                content
            )
        )

        caption_count = len(
            re.findall(
                r"(?i)\bCaption\s*:",
                content
            )
        )

        hashtags_count = len(
            re.findall(
                r"(?i)\bHashtags\s*:",
                content
            )
        )

        cta_count = len(
            re.findall(
                r"(?i)\bCall to Action\s*:",
                content
            )
        )

        if title_count < 3:
            errors.append(
                "Each suggestion must contain a title."
            )

        if caption_count < 3:
            errors.append(
                "Each suggestion must contain a caption."
            )

        if hashtags_count < 3:
            errors.append(
                "Each suggestion must contain hashtags."
            )

        if cta_count < 3:
            errors.append(
                "Each suggestion must contain a call to action."
            )

        # -------------------------------------------------
        # Final result
        # -------------------------------------------------

        is_valid = len(errors) == 0

        return {
            "is_valid": is_valid,
            "errors": errors,
            "warnings": warnings,
        }


    def _build_source_text(
        self,
        campaign,
        knowledge_context
    ):

        company = campaign.company

        product = campaign.product

        source_parts = [
            company.company_name or "",
            company.industry or "",
            company.description or "",
            campaign.campaign_name or "",
            campaign.objective or "",
            campaign.platform or "",
            knowledge_context or "",
        ]

        if product:
            source_parts.extend([
                product.product_name or "",
                product.category or "",
                product.description or "",
                str(product.price or ""),
            ])

        return "\n".join(
            str(part)
            for part in source_parts
            if part
        )