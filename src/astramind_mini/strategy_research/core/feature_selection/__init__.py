"""Public Stage S frozen feature-selection API."""

from .bh import benjamini_hochberg
from .bootstrap import (
    CoreBootstrapResult,
    centered_circular_block_bootstrap,
    selection_seed,
    splitmix64_next,
)
from .clustering import complete_linkage_clusters
from .coverage import (
    CoreCoverageReason,
    CoreDailyCoverageEvidence,
    CoreFoldCoverageEvidence,
    calculate_fold_coverage,
)
from .feature_evidence import (
    subfold_direction_consistent,
    summarize_subfold_rankic,
)
from .joint import (
    build_core_joint_selected_view_manifests,
)
from .joint_models import (
    CoreJointDailyBinding,
    CoreJointFeatureParent,
    CoreJointParentSelection,
    CoreJointSelectedViewManifest,
    CoreJointViewStatus,
)
from .joint_projection import CoreJointMatrixProjection, project_core_joint_selected_matrix
from .metrics import feature_turnover, pair_correlation_evidence
from .models import (
    CoreCorrelationStatus,
    CoreDailyRankICEvidence,
    CoreFeatureSelectionEvidence,
    CoreFeatureSelectionManifest,
    CoreLabelBatchReference,
    CorePairCorrelationEvidence,
    CoreProcessedDayReference,
    CoreSelectionCluster,
    CoreSelectionReason,
    CoreSelectionSpec,
    CoreSubfoldRankICEvidence,
)
from .plan import (
    CoreSelectionFold,
    CoreSelectionPlan,
    CoreSelectionSubfold,
    freeze_core_selection_fold,
    freeze_core_selection_plan,
)
from .priors import (
    STAGE_P_PRIORS_CONTENT_HASH,
    CoreSelectionPriorEntry,
    CoreSelectionPriorManifest,
    load_core_selection_prior_manifest,
)
from .selector import select_core_features
from .statistics import average_ranks, spearman, spearman_by_key

__all__ = [
    "STAGE_P_PRIORS_CONTENT_HASH",
    "CoreBootstrapResult",
    "CoreCorrelationStatus",
    "CoreCoverageReason",
    "CoreDailyCoverageEvidence",
    "CoreDailyRankICEvidence",
    "CoreFeatureSelectionEvidence",
    "CoreFeatureSelectionManifest",
    "CoreFoldCoverageEvidence",
    "CoreJointDailyBinding",
    "CoreJointFeatureParent",
    "CoreJointMatrixProjection",
    "CoreJointParentSelection",
    "CoreJointSelectedViewManifest",
    "CoreJointViewStatus",
    "CoreLabelBatchReference",
    "CorePairCorrelationEvidence",
    "CoreProcessedDayReference",
    "CoreSelectionCluster",
    "CoreSelectionFold",
    "CoreSelectionPlan",
    "CoreSelectionPriorEntry",
    "CoreSelectionPriorManifest",
    "CoreSelectionReason",
    "CoreSelectionSpec",
    "CoreSelectionSubfold",
    "CoreSubfoldRankICEvidence",
    "average_ranks",
    "benjamini_hochberg",
    "build_core_joint_selected_view_manifests",
    "calculate_fold_coverage",
    "centered_circular_block_bootstrap",
    "complete_linkage_clusters",
    "feature_turnover",
    "freeze_core_selection_fold",
    "freeze_core_selection_plan",
    "load_core_selection_prior_manifest",
    "pair_correlation_evidence",
    "project_core_joint_selected_matrix",
    "select_core_features",
    "selection_seed",
    "spearman",
    "spearman_by_key",
    "splitmix64_next",
    "subfold_direction_consistent",
    "summarize_subfold_rankic",
]
