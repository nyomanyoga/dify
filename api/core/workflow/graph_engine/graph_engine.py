"""
QueueBasedGraphEngine - Main orchestrator for queue-based workflow execution.

This engine uses a modular architecture with separated packages following
Domain-Driven Design principles for improved maintainability and testability.
"""

import contextvars
import logging
import queue
from collections.abc import Generator, Mapping
from typing import final

from flask import Flask, current_app

from core.app.entities.app_invoke_entities import InvokeFrom
from core.workflow.entities import GraphRuntimeState
from core.workflow.enums import NodeExecutionType
from core.workflow.graph import Graph
from core.workflow.graph_events import (
    GraphEngineEvent,
    GraphNodeEventBase,
    GraphRunAbortedEvent,
    GraphRunFailedEvent,
    GraphRunStartedEvent,
    GraphRunSucceededEvent,
)
from models.enums import UserFrom

from .command_processing import AbortCommandHandler, CommandProcessor
from .domain import ExecutionContext, GraphExecution
from .entities.commands import AbortCommand
from .error_handling import ErrorHandler
from .event_management import EventHandler, EventManager
from .graph_traversal import EdgeProcessor, SkipPropagator
from .layers.base import Layer
from .orchestration import Dispatcher, ExecutionCoordinator
from .protocols.command_channel import CommandChannel
from .response_coordinator import ResponseStreamCoordinator
from .state_management import UnifiedStateManager
from .worker_management import SimpleWorkerPool

logger = logging.getLogger(__name__)


@final
class GraphEngine:
    """
    Queue-based graph execution engine.

    Uses a modular architecture that delegates responsibilities to specialized
    subsystems, following Domain-Driven Design and SOLID principles.
    """

    def __init__(
        self,
        tenant_id: str,
        app_id: str,
        workflow_id: str,
        user_id: str,
        user_from: UserFrom,
        invoke_from: InvokeFrom,
        call_depth: int,
        graph: Graph,
        graph_config: Mapping[str, object],
        graph_runtime_state: GraphRuntimeState,
        max_execution_steps: int,
        max_execution_time: int,
        command_channel: CommandChannel,
        min_workers: int | None = None,
        max_workers: int | None = None,
        scale_up_threshold: int | None = None,
        scale_down_idle_time: float | None = None,
    ) -> None:
        """Initialize the graph engine with all subsystems and dependencies."""

        # === Domain Models ===
        # Execution context encapsulates workflow execution metadata
        self._execution_context = ExecutionContext(
            tenant_id=tenant_id,
            app_id=app_id,
            workflow_id=workflow_id,
            user_id=user_id,
            user_from=user_from,
            invoke_from=invoke_from,
            call_depth=call_depth,
            max_execution_steps=max_execution_steps,
            max_execution_time=max_execution_time,
        )

        # Graph execution tracks the overall execution state
        self._graph_execution = GraphExecution(workflow_id=workflow_id)

        # === Core Dependencies ===
        # Graph structure and configuration
        self._graph = graph
        self._graph_config = graph_config
        self._graph_runtime_state = graph_runtime_state
        self._command_channel = command_channel

        # === Worker Management Parameters ===
        # Parameters for dynamic worker pool scaling
        self._min_workers = min_workers
        self._max_workers = max_workers
        self._scale_up_threshold = scale_up_threshold
        self._scale_down_idle_time = scale_down_idle_time

        # === Execution Queues ===
        # Queue for nodes ready to execute
        self._ready_queue: queue.Queue[str] = queue.Queue()
        # Queue for events generated during execution
        self._event_queue: queue.Queue[GraphNodeEventBase] = queue.Queue()

        # === State Management ===
        # Unified state manager handles all node state transitions and queue operations
        self._state_manager = UnifiedStateManager(self._graph, self._ready_queue)

        # === Response Coordination ===
        # Coordinates response streaming from response nodes
        self._response_coordinator = ResponseStreamCoordinator(
            variable_pool=self._graph_runtime_state.variable_pool, graph=self._graph
        )

        # === Event Management ===
        # Event manager handles both collection and emission of events
        self._event_manager = EventManager()

        # === Error Handling ===
        # Centralized error handler for graph execution errors
        self._error_handler = ErrorHandler(self._graph, self._graph_execution)

        # === Graph Traversal Components ===
        # Propagates skip status through the graph when conditions aren't met
        self._skip_propagator = SkipPropagator(
            graph=self._graph,
            state_manager=self._state_manager,
        )

        # Processes edges to determine next nodes after execution
        # Also handles conditional branching and route selection
        self._edge_processor = EdgeProcessor(
            graph=self._graph,
            state_manager=self._state_manager,
            response_coordinator=self._response_coordinator,
            skip_propagator=self._skip_propagator,
        )

        # === Event Handler Registry ===
        # Central registry for handling all node execution events
        self._event_handler_registry = EventHandler(
            graph=self._graph,
            graph_runtime_state=self._graph_runtime_state,
            graph_execution=self._graph_execution,
            response_coordinator=self._response_coordinator,
            event_collector=self._event_manager,
            edge_processor=self._edge_processor,
            state_manager=self._state_manager,
            error_handler=self._error_handler,
        )

        # === Command Processing ===
        # Processes external commands (e.g., abort requests)
        self._command_processor = CommandProcessor(
            command_channel=self._command_channel,
            graph_execution=self._graph_execution,
        )

        # Register abort command handler
        abort_handler = AbortCommandHandler()
        self._command_processor.register_handler(
            AbortCommand,
            abort_handler,
        )

        # === Worker Pool Setup ===
        # Capture Flask app context for worker threads
        flask_app: Flask | None = None
        try:
            app = current_app._get_current_object()  # type: ignore
            if isinstance(app, Flask):
                flask_app = app
        except RuntimeError:
            pass

        # Capture context variables for worker threads
        context_vars = contextvars.copy_context()

        # Create worker pool for parallel node execution
        self._worker_pool = SimpleWorkerPool(
            ready_queue=self._ready_queue,
            event_queue=self._event_queue,
            graph=self._graph,
            flask_app=flask_app,
            context_vars=context_vars,
            min_workers=self._min_workers,
            max_workers=self._max_workers,
            scale_up_threshold=self._scale_up_threshold,
            scale_down_idle_time=self._scale_down_idle_time,
        )

        # === Orchestration ===
        # Coordinates the overall execution lifecycle
        self._execution_coordinator = ExecutionCoordinator(
            graph_execution=self._graph_execution,
            state_manager=self._state_manager,
            event_handler=self._event_handler_registry,
            event_collector=self._event_manager,
            command_processor=self._command_processor,
            worker_pool=self._worker_pool,
        )

        # Dispatches events and manages execution flow
        self._dispatcher = Dispatcher(
            event_queue=self._event_queue,
            event_handler=self._event_handler_registry,
            event_collector=self._event_manager,
            execution_coordinator=self._execution_coordinator,
            max_execution_time=self._execution_context.max_execution_time,
            event_emitter=self._event_manager,
        )

        # === Extensibility ===
        # Layers allow plugins to extend engine functionality
        self._layers: list[Layer] = []

        # === Validation ===
        # Ensure all nodes share the same GraphRuntimeState instance
        self._validate_graph_state_consistency()

    def _validate_graph_state_consistency(self) -> None:
        """Validate that all nodes share the same GraphRuntimeState."""
        expected_state_id = id(self._graph_runtime_state)
        for node in self._graph.nodes.values():
            if id(node.graph_runtime_state) != expected_state_id:
                raise ValueError(f"GraphRuntimeState consistency violation: Node '{node.id}' has a different instance")

    def layer(self, layer: Layer) -> "GraphEngine":
        """Add a layer for extending functionality."""
        self._layers.append(layer)
        return self

    def run(self) -> Generator[GraphEngineEvent, None, None]:
        """
        Execute the graph using the modular architecture.

        Returns:
            Generator yielding GraphEngineEvent instances
        """
        try:
            # Initialize layers
            self._initialize_layers()

            # Start execution
            self._graph_execution.start()
            start_event = GraphRunStartedEvent()
            yield start_event

            # Start subsystems
            self._start_execution()

            # Yield events as they occur
            yield from self._event_manager.emit_events()

            # Handle completion
            if self._graph_execution.aborted:
                abort_reason = "Workflow execution aborted by user command"
                if self._graph_execution.error:
                    abort_reason = str(self._graph_execution.error)
                yield GraphRunAbortedEvent(
                    reason=abort_reason,
                    outputs=self._graph_runtime_state.outputs,
                )
            elif self._graph_execution.has_error:
                if self._graph_execution.error:
                    raise self._graph_execution.error
            else:
                yield GraphRunSucceededEvent(
                    outputs=self._graph_runtime_state.outputs,
                )

        except Exception as e:
            yield GraphRunFailedEvent(error=str(e))
            raise

        finally:
            self._stop_execution()

    def _initialize_layers(self) -> None:
        """Initialize layers with context."""
        self._event_manager.set_layers(self._layers)
        for layer in self._layers:
            try:
                layer.initialize(self._graph_runtime_state, self._command_channel)
            except Exception as e:
                logger.warning("Failed to initialize layer %s: %s", layer.__class__.__name__, e)

            try:
                layer.on_graph_start()
            except Exception as e:
                logger.warning("Layer %s failed on_graph_start: %s", layer.__class__.__name__, e)

    def _start_execution(self) -> None:
        """Start execution subsystems."""
        # Start worker pool (it calculates initial workers internally)
        self._worker_pool.start()

        # Register response nodes
        for node in self._graph.nodes.values():
            if node.execution_type == NodeExecutionType.RESPONSE:
                self._response_coordinator.register(node.id)

        # Enqueue root node
        root_node = self._graph.root_node
        self._state_manager.enqueue_node(root_node.id)
        self._state_manager.start_execution(root_node.id)

        # Start dispatcher
        self._dispatcher.start()

    def _stop_execution(self) -> None:
        """Stop execution subsystems."""
        self._dispatcher.stop()
        self._worker_pool.stop()
        # Don't mark complete here as the dispatcher already does it

        # Notify layers
        logger = logging.getLogger(__name__)

        for layer in self._layers:
            try:
                layer.on_graph_end(self._graph_execution.error)
            except Exception as e:
                logger.warning("Layer %s failed on_graph_end: %s", layer.__class__.__name__, e)

    # Public property accessors for attributes that need external access
    @property
    def graph_runtime_state(self) -> GraphRuntimeState:
        """Get the graph runtime state."""
        return self._graph_runtime_state
