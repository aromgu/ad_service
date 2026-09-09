from __future__ import annotations

import argparse
import json
from pathlib import Path

from ad_service.api.schemas.generation import GenerationRequest
from ad_service.evaluation import aggregate_scores, create_score_sheet
from ad_service.factory import (
    create_background_remover,
    create_copy_provider,
    create_image_provider,
)
from ad_service.pipelines.inference import GenerationPipeline


def _load_request(path: Path) -> GenerationRequest:
    return GenerationRequest.model_validate_json(path.read_text(encoding="utf-8"))


def _pipeline(args: argparse.Namespace) -> GenerationPipeline:
    return GenerationPipeline(
        copy_provider=create_copy_provider(args.copy_provider),
        image_provider=create_image_provider(args.image_provider, args.quality),
        background_remover=create_background_remover(args.remover),
        output_root=args.output,
        budget_cap_usd=args.budget_cap,
    )


def _add_provider_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--copy-provider",
        default="mock",
        choices=["mock", "gpt-5.4-mini", "gpt-5.4-nano", "qwen3-8b"],
    )
    parser.add_argument(
        "--image-provider",
        default="mock",
        choices=["mock", "gpt-image-2", "flux2-klein-4b"],
    )
    parser.add_argument(
        "--remover",
        # 기본 Mock 스모크 테스트는 GPU 없이 돌아가야 하므로 simple을 유지합니다.
        # 실제 모델 실행에서는 --remover auto를 지정해 자동 라우팅을 켭니다.
        default="simple",
        choices=["auto", "simple", "birefnet", "sam2"],
        help="auto는 선택 박스가 있으면 SAM2, 없으면 BiRefNet을 사용합니다.",
    )
    parser.add_argument("--quality", default="medium", choices=["low", "medium", "high"])
    parser.add_argument("--budget-cap", type=float, default=10.0)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--output", type=Path, default=Path("data/outputs/baseline_v1"))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ad-service")
    subparsers = parser.add_subparsers(dest="command", required=True)

    generate = subparsers.add_parser("generate")
    generate.add_argument("--input", type=Path, required=True)
    _add_provider_args(generate)

    batch = subparsers.add_parser("batch")
    batch.add_argument("--manifest", type=Path, required=True)
    _add_provider_args(batch)

    score_sheet = subparsers.add_parser("make-score-sheet")
    score_sheet.add_argument("--results", type=Path, required=True)
    score_sheet.add_argument("--output", type=Path, required=True)

    aggregate = subparsers.add_parser("aggregate-scores")
    aggregate.add_argument("--scores", type=Path, required=True)
    aggregate.add_argument("--output", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> None:
    """명령행 인자를 읽고 선택한 작업을 실행합니다.

    평소 터미널에서 실행할 때는 ``argv``를 전달하지 않습니다. 테스트에서는 인자 목록을
    직접 넣을 수 있게 만들어 실제 명령을 실행하지 않고도 CLI 전체 흐름을 확인합니다.
    """

    args = build_parser().parse_args(argv)
    if args.command == "make-score-sheet":
        rows = create_score_sheet(args.results, args.output)
        print(json.dumps({"rows": rows, "output": str(args.output)}))
        return
    if args.command == "aggregate-scores":
        summaries = aggregate_scores(args.scores, args.output)
        print(json.dumps(summaries, ensure_ascii=False, indent=2))
        return

    pipeline = _pipeline(args)
    if args.command == "generate":
        result = pipeline.generate(_load_request(args.input), seed=args.seed, base_dir=Path.cwd())
        print(result.model_dump_json(indent=2))
        return
    payload = json.loads(args.manifest.read_text(encoding="utf-8"))
    results = [
        pipeline.generate(
            GenerationRequest.model_validate(item),
            seed=args.seed,
            base_dir=Path.cwd(),
        )
        for item in payload
    ]
    print(json.dumps({"completed": len(results), "output": str(args.output)}))


if __name__ == "__main__":
    main()
