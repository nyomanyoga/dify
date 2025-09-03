"""
Event handler implementations for different event types.
"""

import logging
from typing import TYPE_CHECKING, final

from core.workflow.entities import GraphRuntimeState
from core.workflow.enums import NodeExecutionType
from core.workflow.graph import Graph
from core.workflow.graph_events import (
    GraphNodeEventBase,
    NodeRunAgentLogEvent,
    NodeRunExceptionEvent,
    NodeRunFailedEvent,
    NodeRunIterationFailedEvent,
    NodeRunIterationNextEvent,
    NodeRunIterationStartedEvent,
    NodeRunIterationSucceededEvent,
    NodeRunLoopFailedEvent,
    NodeRunLoopNextEvent,
    NodeRunLoopStartedEvent,
    NodeRunLoopSucceededEvent,
    NodeRunRetryEvent,
    NodeRunStartedEvent,
    NodeRunStreamChunkEvent,
    NodeRunSucceededEvent,
)

from ..domain.graph_execution import GraphExecution
from ..response_coordinator import ResponseStreamCoordinator

if TYPE_CHECKING:
    from ..error_handling import ErrorHandler
    from ..graph_traversal import EdgeProcessor
    from ..state_management import UnifiedStateManager
    from .event_manager import EventManager

logger = logging.getLogger(__name__)


@final
class EventHandler:
    """
    Registry of event handlers for different event types.

    This centralizes the business logic for handling specific events,
    keeping it separate from the routing and collection infrastructure.
    """

    def __init__(
        self,
        graph: Graph,
        graph_runtime_state: GraphRuntimeState,
        graph_execution: GraphExecution,
        response_coordinator: ResponseStreamCoordinator,
        event_collector: "EventManager",
        edge_processor: "EdgeProcessor",
        state_manager: "UnifiedStateManager",
        error_handler: "ErrorHandler",
    ) -> None:
        """
        Initialize the event handler registry.

        Args:
            graph: The workflow graph
            graph_runtime_state: Runtime state with variable pool
            graph_execution: Graph execution aggregate
            response_coordinator: Response stream coordinator
            event_collector: Event manager for collecting events
            edge_processor: Edge processor for edge traversal
            state_manager: Unified state manager
            error_handler: Error handler
        """
        self._graph = graph
        self._graph_runtime_state = graph_runtime_state
        self._graph_execution = graph_execution
        self._response_coordinator = response_coordinator
        self._event_collector = event_collector
        self._edge_processor = edge_processor
        self._state_manager = state_manager
        self._error_handler = error_handler

    def handle_event(self, event: GraphNodeEventBase) -> None:
        """
        Handle any node event by dispatching to the appropriate handler.

        Args:
            event: The event to handle
        """
        # Events in loops or iterations are always collected
        if event.in_loop_id or event.in_iteration_id:
            self._event_collector.collect(event)
            return

        # Handle specific event types
        if isinstance(event, NodeRunStartedEvent):
            self._handle_node_started(event)
        elif isinstance(event, NodeRunStreamChunkEvent):
            self._handle_stream_chunk(event)
        elif isinstance(event, NodeRunSucceededEvent):
            self._handle_node_succeeded(event)
        elif isinstance(event, NodeRunFailedEvent):
            self._handle_node_failed(event)
        elif isinstance(event, NodeRunExceptionEvent):
            self._handle_node_exception(event)
        elif isinstance(event, NodeRunRetryEvent):
            self._handle_node_retry(event)
        elif isinstance(
            event,
            (
                NodeRunIterationStartedEvent,
                NodeRunIterationNextEvent,
                NodeRunIterationSucceededEvent,
                NodeRunIterationFailedEvent,
                NodeRunLoopStartedEvent,
                NodeRunLoopNextEvent,
                NodeRunLoopSucceededEvent,
                NodeRunLoopFailedEvent,
                NodeRunAgentLogEvent,
            ),
        ):
            # Iteration and loop events are collected directly
            self._event_collector.collect(event)
        else:
            # Collect unhandled events
            self._event_collector.collect(event)
            logger.warning("Unhandled event type: %s", type(event).__name__)

    def _handle_node_started(self, event: NodeRunStartedEvent) -> None:
        """
        Handle node started event.

        Args:
            event: The node started event
        """
        # Track execution in domain model
        node_execution = self._graph_execution.get_or_create_node_execution(event.node_id)
        node_execution.mark_started(event.id)

        # Track in response coordinator for stream ordering
        self._response_coordinator.track_node_execution(event.node_id, event.id)

        # Collect the event
        self._event_collector.collect(event)

    def _handle_stream_chunk(self, event: NodeRunStreamChunkEvent) -> None:
        """
        Handle stream chunk event with full processing.

        Args:
            event: The stream chunk event
        """
        # Process with response coordinator
        streaming_events = list(self._response_coordinator.intercept_event(event))

        # Collect all events
        for stream_event in streaming_events:
            self._event_collector.collect(stream_event)

    def _handle_node_succeeded(self, event: NodeRunSucceededEvent) -> None:
        """
        Handle node success by coordinating subsystems.

        This method coordinates between different subsystems to process
        node completion, handle edges, and trigger downstream execution.

        Args:
            event: The node succeeded event
        """
        # Update domain model
        node_execution = self._graph_execution.get_or_create_node_execution(event.node_id)
        node_execution.mark_taken()

        # Store outputs in variable pool
        self._store_node_outputs(event)

        # Forward to response coordinator and emit streaming events
        streaming_events = self._response_coordinator.intercept_event(event)
        for stream_event in streaming_events:
            self._event_collector.collect(stream_event)

        # Process edges and get ready nodes
        node = self._graph.nodes[event.node_id]
        if node.execution_type == NodeExecutionType.BRANCH:
            ready_nodes, edge_streaming_events = self._edge_processor.handle_branch_completion(
                event.node_id, event.node_run_result.edge_source_handle
            )
        else:
            ready_nodes, edge_streaming_events = self._edge_processor.process_node_success(event.node_id)

        # Collect streaming events from edge processing
        for edge_event in edge_streaming_events:
            self._event_collector.collect(edge_event)

        # Enqueue ready nodes
        for node_id in ready_nodes:
            self._state_manager.enqueue_node(node_id)
            self._state_manager.start_execution(node_id)

        # Update execution tracking
        self._state_manager.finish_execution(event.node_id)

        # Handle response node outputs
        if node.execution_type == NodeExecutionType.RESPONSE:
            self._update_response_outputs(event)

        # Collect the event
        self._event_collector.collect(event)

    def _handle_node_failed(self, event: NodeRunFailedEvent) -> None:
        """
        Handle node failure using error handler.

        Args:
            event: The node failed event
        """
        # Update domain model
        node_execution = self._graph_execution.get_or_create_node_execution(event.node_id)
        node_execution.mark_failed(event.error)

        result = self._error_handler.handle_node_failure(event)

        if result:
            # Process the resulting event (retry, exception, etc.)
            self.handle_event(result)
        else:
            # Abort execution
            self._graph_execution.fail(RuntimeError(event.error))
            self._event_collector.collect(event)
            self._state_manager.finish_execution(event.node_id)

    def _handle_node_exception(self, event: NodeRunExceptionEvent) -> None:
        """
        Handle node exception event (fail-branch strategy).

        Args:
            event: The node exception event
        """
        # Node continues via fail-branch, so it's technically "succeeded"
        node_execution = self._graph_execution.get_or_create_node_execution(event.node_id)
        node_execution.mark_taken()

    def _handle_node_retry(self, event: NodeRunRetryEvent) -> None:
        """
        Handle node retry event.

        Args:
            event: The node retry event
        """
        node_execution = self._graph_execution.get_or_create_node_execution(event.node_id)
        node_execution.increment_retry()

    def _store_node_outputs(self, event: NodeRunSucceededEvent) -> None:
        """
        Store node outputs in the variable pool.

        Args:
            event: The node succeeded event containing outputs
        """
        for variable_name, variable_value in event.node_run_result.outputs.items():
            self._graph_runtime_state.variable_pool.add((event.node_id, variable_name), variable_value)

    def _update_response_outputs(self, event: NodeRunSucceededEvent) -> None:
        """Update response outputs for response nodes."""
        # TODO: Design a mechanism for nodes to notify the engine about how to update outputs
        # in runtime state, rather than allowing nodes to directly access runtime state.
        for key, value in event.node_run_result.outputs.items():
            if key == "answer":
                existing = self._graph_runtime_state.outputs.get("answer", "")
                if existing:
                    self._graph_runtime_state.outputs["answer"] = f"{existing}{value}"
                else:
                    self._graph_runtime_state.outputs["answer"] = value
            else:
                self._graph_runtime_state.outputs[key] = value
